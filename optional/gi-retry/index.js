'use strict';

const TableStore = require('tablestore');
const OpenAPI = require('@alicloud/openapi-client');
const FNF20190315 = require('@alicloud/fnf20190315');
const dayjs = require('dayjs');
const utc = require('dayjs/plugin/utc');
const timezone = require('dayjs/plugin/timezone');
dayjs.extend(utc);
dayjs.extend(timezone);

const {
  REGION,
  FLOW_NAME,
  ECS_INSTANCE_ID,
  WINDOW_SECONDS = '900',
  K_MAX = '2',
  OTS_ENDPOINT,
  OTS_INSTANCE,
  OTS_TABLE = 'gi_retry',
  RETRY_KEY = 'global',
  DATE_TZ = 'Asia/Shanghai'
} = process.env;

/* ====== logging utils ====== */
function mask(s, keep = 4) {
  if (!s || typeof s !== 'string') return s;
  if (s.length <= keep) return '*'.repeat(s.length);
  return s.slice(0, keep) + '***';
}

function logEnvOnce() {
  if (logEnvOnce.done) return;
  logEnvOnce.done = true;
  console.log(
    '[env]',
    JSON.stringify({
      REGION,
      FLOW_NAME,
      ECS_INSTANCE_ID: mask(ECS_INSTANCE_ID),
      WINDOW_SECONDS,
      K_MAX,
      OTS_ENDPOINT,
      OTS_INSTANCE,
      OTS_TABLE,
      RETRY_KEY,
      DATE_TZ
    })
  );
  console.log('[env] process.versions:', JSON.stringify(process.versions));
  console.log('[env] node pid/cwd:', process.pid, process.cwd());
}

function todayStr() {
  return dayjs().tz(DATE_TZ).format('YYYY-MM-DD');
}

// ---- LOG ONLY: 统一打印消息预览（长度 + 前后预览）
function logMsgPreview(tag, msg, max = 240) {
  try {
    const s = typeof msg === 'string' ? msg : (msg == null ? '' : String(msg));
    const len = s.length;
    if (len <= max) {
      console.log(`[${tag}] msg(len=${len}):`, s);
      return;
    }
    const head = s.slice(0, Math.floor(max / 2));
    const tail = s.slice(-Math.floor(max / 2));
    console.log(`[${tag}] msg(len=${len}) head:`, head);
    console.log(`[${tag}] msg(len=${len}) tail:`, tail);
  } catch (e) {
    console.log(`[${tag}] preview error:`, String(e));
  }
}

function parseText(req) {
  const h = req.headers || {};
  const ct = (h['content-type'] || h['Content-Type'] || '').toLowerCase();
  const raw = req.body && req.body.length ? req.body.toString('utf8') : '';
  console.log('[parseText] content-type:', ct || '(empty)', 'bodyLen:', raw.length);
  if (ct.includes('application/json')) {
    try {
      const o = JSON.parse(raw);
      const out = o.text || o.content || raw;
      console.log('[parseText] json ok. keys:', Object.keys(o));
      logMsgPreview('parseText.out', out);
      return out;
    } catch (e) {
      console.log('[parseText] json parse fail:', String(e));
      logMsgPreview('parseText.raw-fallback', raw);
      return raw;
    }
  }
  logMsgPreview('parseText.raw', raw);
  return raw;
}

function isException(msg) {
  const r = typeof msg === 'string' && msg.includes('异常');
  console.log('[isException]', r, 'msgHas异常=', (typeof msg === 'string' && msg.indexOf('异常') >= 0));
  return r;
}

function otsClient(context) {
  console.log('[otsClient] init',
    JSON.stringify({
      endpoint: OTS_ENDPOINT,
      instancename: OTS_INSTANCE,
      credExist: !!(context && context.credentials),
      akIdMask: context && context.credentials && mask(context.credentials.accessKeyId),
      hasSts: !!(context && context.credentials && context.credentials.securityToken)
    })
  );
  return new TableStore.Client({
    endpoint: OTS_ENDPOINT,
    instancename: OTS_INSTANCE,
    accessKeyId: context.credentials.accessKeyId,
    accessKeySecret: context.credentials.accessKeySecret,
    stsToken: context.credentials.securityToken
  });
}

// 符合 TableStore UpdateType 结构 + 正确主键写法
async function otsTryIncrement(client, pk, today, kmax) {
  console.log('[otsTryIncrement] enter', { pk, today, kmax });

  const AND = new TableStore.CompositeCondition(TableStore.LogicalOperator.AND);
  const kmaxLong = TableStore.Long.fromNumber(Number(kmax));
  AND.addSubCondition(
    new TableStore.SingleColumnCondition(
      'last_retry_date',
      today,
      TableStore.ComparatorType.EQUAL,
      true
    )
  );
  AND.addSubCondition(
    new TableStore.SingleColumnCondition(
      'retry_count',
      kmaxLong,
      TableStore.ComparatorType.LESS_THAN,
      true
    )
  );

  try {
    console.log('[otsTryIncrement] path1 try: date==today & retry_count<kmax, INCREMENT + PUT ts');
    await client.updateRow({
      tableName: OTS_TABLE,
      condition: new TableStore.Condition(TableStore.RowExistenceExpectation.IGNORE, AND),
      primaryKey: [{ pk }], // 单列主键
      updateOfAttributeColumns: [
        { INCREMENT: [{ retry_count: TableStore.Long.fromNumber(1) }] },
        { PUT: [{ last_retry_at: new Date().toISOString() }] }
      ]
    });
    console.log('[otsTryIncrement] path1 ok');
    return true;
  } catch (e1) {
    console.log(
      '[otsTryIncrement] path1 no-op or fail:',
      e1 && e1.code,
      String((e1 && e1.message) || e1)
    );
  }

  const NE = new TableStore.SingleColumnCondition(
    'last_retry_date',
    today,
    TableStore.ComparatorType.NOT_EQUAL,
    true
  );

  try {
    console.log('[otsTryIncrement] path2 try: date!=today, PUT(date,t=1,ts)');
    await client.updateRow({
      tableName: OTS_TABLE,
      condition: new TableStore.Condition(TableStore.RowExistenceExpectation.IGNORE, NE),
      primaryKey: [{ pk }], // 单列主键
      updateOfAttributeColumns: [
        {
          PUT: [
            { last_retry_date: today },
            { retry_count: TableStore.Long.fromNumber(1) },
            { last_retry_at: new Date().toISOString() }
          ]
        }
      ]
    });
    console.log('[otsTryIncrement] path2 ok');
    return true;
  } catch (e2) {
    console.log(
      '[otsTryIncrement] path2 fail:',
      e2 && e2.code,
      String((e2 && e2.message) || e2)
    );
    return false;
  }
}

function fnfClient(context) {
  // 1) 允许用环境变量强制覆盖（推荐在控制台/部署里配）
  const internalDefault = `${REGION}-internal.fnf.aliyuncs.com`; // 你日志中的样式
  const publicDefault   = `fnf.${REGION}.aliyuncs.com`;           // 公网样式（SDK常用）
  const endpoint = process.env.FNF_ENDPOINT || internalDefault;

  // 打印我们“准备”使用的 endpoint
  console.log('[fnfClient] init', JSON.stringify({
    region: REGION,
    endpoint,
    publicFallback: publicDefault,
    credExist: !!(context && context.credentials),
    akIdMask: context && context.credentials && mask(context.credentials.accessKeyId),
    hasSts: !!(context && context.credentials && context.credentials.securityToken)
  }));

  const config = new OpenAPI.Config({
    accessKeyId: context.credentials.accessKeyId,
    accessKeySecret: context.credentials.accessKeySecret,
    securityToken: context.credentials.securityToken,
    regionId: REGION,
    endpoint, // 2) 真实传入我们想要的 endpoint（与日志一致）
  });

  const client = new FNF20190315.default(config);

  // 3) 个别 Tea SDK 版本还需要再显式覆盖一次
  client.endpoint = endpoint;

  // 4) 附带一个轻量的“备用端点”策略：封装一次 startExecution（可选）
  client._startExecutionWithFallback = async (req) => {
    try {
      return await client.startExecution(req);
    } catch (e) {
      // 仅当 DNS 解析失败且当前不是公网域名时，切到公网域名再试一次
      const msg = String(e && e.message || e);
      if (/ENOTFOUND/i.test(msg) && endpoint !== publicDefault) {
        console.log('[fnfClient] ENOTFOUND on', endpoint, '-> fallback to public:', publicDefault);
        client.endpoint = publicDefault;
        client.config.endpoint = publicDefault; // 保险再写一次
        return await client.startExecution(req);
      }
      throw e;
    }
  };

  console.log('[fnfClient] ready', JSON.stringify({
    region: REGION,
    usingEndpoint: client.endpoint
  }));

  return client;
}

async function startFlow(client) {
  const input = { ecsInstanceId: ECS_INSTANCE_ID, windowSeconds: Number(WINDOW_SECONDS) };
  console.log('[startFlow] request', {
    flowName: FLOW_NAME,
    input: { ...input, ecsInstanceId: mask(ECS_INSTANCE_ID) }
  });
  const req = new FNF20190315.StartExecutionRequest({
    flowName: FLOW_NAME,
    input: JSON.stringify(input)
  });
  const t0 = Date.now();
  const resp = await (client._startExecutionWithFallback
    ? client._startExecutionWithFallback(req)
    : client.startExecution(req));  
  const dt = Date.now() - t0;
  console.log('[startFlow] response(ms=', dt, '):', JSON.stringify(resp));
  return resp;
}

function getBody(req) {
  if (!req || req.body == null) {
    console.log('[getBody] empty body');
    return Buffer.alloc(0);
  }
  const b = req.body;
  const base64 = req.isBase64Encoded === true || req.isBase64 === true;

  if (Buffer.isBuffer(b)) {
    console.log('[getBody] buffer', { len: b.length, base64 });
    return b;
  }
  if (typeof b === 'string') {
    const buf = Buffer.from(b, base64 ? 'base64' : 'utf8');
    console.log('[getBody] string -> buffer', { srcLen: b.length, outLen: buf.length, base64 });
    return buf;
  }
  if (typeof b === 'object') {
    const s = JSON.stringify(b);
    console.log('[getBody] object -> buffer', { jsonLen: s.length });
    return Buffer.from(s, 'utf8');
  }

  const s = String(b);
  console.log('[getBody] other -> buffer', { strLen: s.length });
  return Buffer.from(s, 'utf8');
}

function send(_, code, obj) {
  const out = {
    statusCode: code,
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(obj)
  };
  console.log('[send]', code, out.body.slice(0, 500));
  return out;
}

// HTTP/Event 通用入口
module.exports.handler = async function (...args) {
  const isHttp =
    args.length === 3 &&
    args[0] &&
    typeof args[0] === 'object' &&
    ('body' in args[0] || 'headers' in args[0]);

  const context = isHttp ? args[2] : args[1];
  const rid = Date.now().toString(36) + Math.random().toString(16).slice(2, 8);

  logEnvOnce();
  console.log('[handler] rid=', rid, 'isHttp=', isHttp, 'requestId=', context && context.requestId);

  const tStart = Date.now();
  try {
    if (isHttp) {
      const req = args[0],
        res = args[1];
      console.log(
        '[handler] start HTTP',
        JSON.stringify({
          rid,
          method: req && req.method,
          path: req && req.path,
          headerKeys: req && req.headers ? Object.keys(req.headers) : []
        })
      );

      req.body = getBody(req);
      console.log('[handler][HTTP] getBody done, len=', req.body ? req.body.length : 0);

      const msg = parseText({ headers: req.headers, body: req.body });
      logMsgPreview('handler.msg(HTTP)', msg);
      const hit = isException(msg);
      console.log('[handler][HTTP] isException=', hit);

      if (!hit) {
        console.log('[handler][HTTP] decide: skipped');
        return send(res, 200, { ok: true, skipped: true, rid });
      }

      console.log('[handler][HTTP] create ots client...');
      const ots = otsClient(context);
      console.log('[handler][HTTP] try increment quota...', {
        pk: process.env.RETRY_KEY || 'global',
        today: todayStr(),
        kmax: Number(K_MAX)
      });
      const ok = await otsTryIncrement(
        ots,
        process.env.RETRY_KEY || 'global',
        todayStr(),
        Number(K_MAX)
      );
      console.log('[handler][HTTP] otsTryIncrement result:', ok);
      if (!ok) {
        console.log('[handler][HTTP] decide: quota_exceeded');
        return send(res, 200, { ok: true, quota_exceeded: true, rid });
      }

      console.log('[handler][HTTP] create fnf client & start flow...');
      const fnf = fnfClient(context);
      await startFlow(fnf);
      console.log('[handler][HTTP] decide: triggered');
      return send(res, 200, { ok: true, triggered: true, rid });
    }

    // EVENT 分支
    const event = args[0];
    console.log('[handler] start EVENT', JSON.stringify({
      rid,
      type: typeof event,
      isProxy: !!(event && typeof event === 'object' && 'body' in event),
      hasHeaders: !!(event && typeof event === 'object' && 'headers' in event)
    }));

    let headers = {};
    let bodyBuf = Buffer.alloc(0);

    if (event && typeof event === 'object' && 'body' in event) {
      headers = event.headers || {};
      const base64 = event.isBase64Encoded === true || event.isBase64 === true;
      if (typeof event.body === 'string')
        bodyBuf = Buffer.from(event.body, base64 ? 'base64' : 'utf8');
      else if (Buffer.isBuffer(event.body)) bodyBuf = event.body;
      else if (event.body != null) bodyBuf = Buffer.from(String(event.body), 'utf8');
      console.log('[event] proxy bodyLen:', bodyBuf.length, 'base64:', !!base64, 'headerKeys:', Object.keys(headers));
    } else {
      if (Buffer.isBuffer(event)) bodyBuf = event;
      else if (typeof event === 'string') bodyBuf = Buffer.from(event, 'utf8');
      else if (event != null) bodyBuf = Buffer.from(JSON.stringify(event), 'utf8');
      console.log('[event] bodyLen:', bodyBuf.length);
    }

    const msg = parseText({ headers, body: bodyBuf });
    logMsgPreview('handler.msg(EVENT)', msg);
    const hit = isException(msg);
    console.log('[handler][EVENT] isException=', hit);
    if (!hit) {
      console.log('[handler][EVENT] decide: skipped');
      return JSON.stringify({ ok: true, skipped: true, rid });
    }

    console.log('[handler][EVENT] create ots client...');
    const ots = otsClient(context);
    console.log('[handler][EVENT] try increment quota...', {
      pk: process.env.RETRY_KEY || 'global',
      today: todayStr(),
      kmax: Number(K_MAX)
    });
    const ok = await otsTryIncrement(
      ots,
      process.env.RETRY_KEY || 'global',
      todayStr(),
      Number(K_MAX)
    );
    console.log('[handler][EVENT] otsTryIncrement result:', ok);
    if (!ok) {
      console.log('[handler][EVENT] decide: quota_exceeded');
      return JSON.stringify({ ok: true, quota_exceeded: true, rid });
    }

    console.log('[handler][EVENT] create fnf client & start flow...');
    const fnf = fnfClient(context);
    await startFlow(fnf);
    console.log('[handler][EVENT] decide: triggered');
    return JSON.stringify({ ok: true, triggered: true, rid });
  } catch (err) {
    const msg = String((err && err.message) || err);
    const stack = err && err.stack ? String(err.stack).split('\n').slice(0, 10).join('\n') : '';
    console.error('[handler] error rid=', rid, msg, '\n', stack);

    if (args.length === 3 && args[1]) return send(args[1], 500, { ok: false, error: msg, rid });
    return JSON.stringify({ ok: false, error: msg, rid });
  } finally {
    const dt = Date.now() - tStart;
    console.log('[handler] end rid=', rid, 'costMs=', dt, 'requestId=', context && context.requestId);
  }
};
