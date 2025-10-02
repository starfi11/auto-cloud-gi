'use strict';
const TableStore = require('tablestore');
const OpenAPI = require('@alicloud/openapi-client');
const FNF20190315 = require('@alicloud/fnf20190315');
const dayjs = require('dayjs');
const utc = require('dayjs/plugin/utc');
const timezone = require('dayjs/plugin/timezone');
dayjs.extend(utc); dayjs.extend(timezone);

const {
  REGION, FLOW_NAME, ECS_INSTANCE_ID, WINDOW_SECONDS = '900',
  K_MAX = '2', OTS_ENDPOINT, OTS_INSTANCE, OTS_TABLE = 'gi_retry',
  RETRY_KEY = 'global', DATE_TZ = 'Asia/Shanghai'
} = process.env;

function todayStr() { return dayjs().tz(DATE_TZ).format('YYYY-MM-DD'); }

function parseText(req) {
  const ct = (req.headers['content-type'] || '').toLowerCase();
  const raw = req.body && req.body.length ? req.body.toString('utf8') : '';
  if (ct.includes('application/json')) {
    try { const o = JSON.parse(raw); return o.text || o.content || raw; } catch { return raw; }
  }
  return raw;
}

function isException(msg) { return typeof msg === 'string' && msg.includes('运行：异常'); }

function otsClient(context) {
  return new TableStore.Client({
    endpoint: OTS_ENDPOINT,
    instancename: OTS_INSTANCE,
    accessKeyId: context.credentials.accessKeyId,
    accessKeySecret: context.credentials.accessKeySecret,
    stsToken: context.credentials.securityToken
  });
}

// 当日自增；跨日首条重置为1，并写入 last_retry_at（原子条件保证并发安全）
async function otsTryIncrement(client, pk, today, kmax) {
  const AND = new TableStore.CompositeCondition(TableStore.LogicalOperator.AND);
  AND.addSubCondition(new TableStore.SingleColumnCondition('last_retry_date', today, TableStore.ComparatorType.EQUAL, true));
  AND.addSubCondition(new TableStore.SingleColumnCondition('retry_count', Number(kmax), TableStore.ComparatorType.LESS_THAN, true));
  try {
    await client.updateRow({
      tableName: OTS_TABLE,
      condition: new TableStore.Condition(TableStore.RowExistenceExpectation.IGNORE, AND),
      primaryKey: [{ name: 'pk', value: pk }],
      updateOfAttributeColumns: [
        { type: 'INCREMENT', name: 'retry_count', value: [1] },
        { type: 'PUT', name: 'last_retry_at', value: new Date().toISOString() }
      ]
    });
    return true;
  } catch (_) { /* fallthrough */ }

  // 跨日/首写：仅当 last_retry_date != today
  const NE = new TableStore.SingleColumnCondition('last_retry_date', today, TableStore.ComparatorType.NOT_EQUAL, true);
  try {
    await client.updateRow({
      tableName: OTS_TABLE,
      condition: new TableStore.Condition(TableStore.RowExistenceExpectation.IGNORE, NE),
      primaryKey: [{ name: 'pk', value: pk }],
      updateOfAttributeColumns: [
        { type: 'PUT', name: 'last_retry_date', value: today },
        { type: 'PUT', name: 'retry_count', value: 1 },
        { type: 'PUT', name: 'last_retry_at', value: new Date().toISOString() }
      ]
    });
    return true;
  } catch (_) {
    return false;
  }
}

function fnfClient(context) {
  const config = new OpenAPI.Config({
    accessKeyId: context.credentials.accessKeyId,
    accessKeySecret: context.credentials.accessKeySecret,
    securityToken: context.credentials.securityToken,
    regionId: REGION,
    endpoint: `fnf.${REGION}.aliyuncs.com`
  });
  return new FNF20190315.default(config);
}

async function startFlow(client) {
  const req = new FNF20190315.StartExecutionRequest({
    flowName: FLOW_NAME,
    input: JSON.stringify({ ecsInstanceId: ECS_INSTANCE_ID, windowSeconds: Number(WINDOW_SECONDS) })
  });
  return client.startExecution(req);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (c) => chunks.push(c));
    req.on('end', () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

// Web 函数入口（平台签名在网关已完成）
module.exports.handler = async (req, res, context) => {
  try {
    if (!req.body) req.body = await readBody(req);

    const msg = parseText(req);
    if (!isException(msg)) {
      res.setStatusCode(200); res.setHeader('content-type', 'application/json');
      return res.send(JSON.stringify({ ok: true, skipped: true }));
    }

    const ots = otsClient(context);
    const ok = await otsTryIncrement(ots, process.env.RETRY_KEY || 'global', todayStr(), Number(K_MAX));
    if (!ok) {
      res.setStatusCode(200); res.setHeader('content-type', 'application/json');
      return res.send(JSON.stringify({ ok: true, quota_exceeded: true }));
    }

    const fnf = fnfClient(context);
    await startFlow(fnf);

    res.setStatusCode(200); res.setHeader('content-type', 'application/json');
    return res.send(JSON.stringify({ ok: true, triggered: true }));
  } catch (err) {
    res.setStatusCode(500); res.setHeader('content-type', 'application/json');
    return res.send(JSON.stringify({ ok: false, error: String((err && err.message) || err) }));
  }
};
