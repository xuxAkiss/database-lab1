// Project environment administration only; no business collections or test writes.
const admin = db.getSiblingDB("admin");
const mode = process.env.WORK1_MONGO_MODE;
const expectedSet = "work1DevRs";
const expectedHost = "127.0.0.1:27018";
const normalize = value => String(value).replace(/\\/g, "/").toLowerCase();
function requireOk(result, label) {
  if (result.ok !== 1) throw new Error(label + ": " + JSON.stringify(result));
  return result;
}
requireOk(admin.runCommand({ ping: 1 }), "ping");
const options = requireOk(admin.runCommand({ getCmdLineOpts: 1 }), "getCmdLineOpts").parsed;
if (normalize(options.storage?.dbPath) !== normalize(process.env.WORK1_MONGO_DATA) ||
    options.net?.port !== 27018 || options.net?.bindIp !== "127.0.0.1" ||
    options.replication?.replSetName !== expectedSet) {
  throw new Error("Server paths/network/replica-set options do not match this project.");
}
let status;
try {
  status = admin.runCommand({ replSetGetStatus: 1 });
} catch (error) {
  if (error.code !== 94) throw error;
  status = { ok: 0, code: 94 };
}
if (status.ok !== 1) {
  if (mode !== "initialize" || process.env.WORK1_MONGO_INIT_ALLOWED !== "true" || status.code !== 94) {
    throw new Error("Replica set is unavailable; initialization is not authorized for this state.");
  }
  requireOk(admin.runCommand({
    replSetInitiate: { _id: expectedSet, members: [{ _id: 0, host: expectedHost }] }
  }), "replSetInitiate");
  print("Initialized new project replica set; MongoDB internal replication data was created.");
}
const configuration = requireOk(admin.runCommand({ replSetGetConfig: 1 }), "replSetGetConfig").config;
if (configuration._id !== expectedSet || configuration.members.length !== 1 ||
    configuration.members[0].host !== expectedHost) {
  throw new Error("Existing replica-set configuration differs. No reconfiguration was attempted.");
}
if (mode === "shutdown") {
  print("Requesting graceful shutdown of the verified project instance.");
  try {
    admin.runCommand({ shutdown: 1, timeoutSecs: 10 });
  } catch (error) {
    if (!/MongoNetworkError|MongoServerSelectionError/.test(error.name)) throw error;
    print("Connection closed during shutdown; the PowerShell script will verify process exit.");
  }
} else {
  const deadline = Date.now() + 45000;
  let hello;
  do {
    hello = requireOk(admin.runCommand({ hello: 1 }), "hello");
    if (hello.isWritablePrimary && hello.setName === expectedSet) break;
    sleep(500);
  } while (Date.now() < deadline);
  if (!hello.isWritablePrimary || hello.setName !== expectedSet) {
    throw new Error("Writable primary was not ready within 45 seconds.");
  }
  status = requireOk(admin.runCommand({ replSetGetStatus: 1 }), "replSetGetStatus");
  const build = requireOk(admin.runCommand({ buildInfo: 1 }), "buildInfo");
  print(JSON.stringify({
    ping: requireOk(admin.runCommand({ ping: 1 }), "ping").ok,
    serverVersion: build.version,
    replicaSet: hello.setName,
    isWritablePrimary: hello.isWritablePrimary,
    members: status.members.map(m => ({ name: m.name, state: m.stateStr, health: m.health })),
    dataPath: options.storage.dbPath,
    transactionDeploymentPrerequisite: "replica set ready; business transactions NOT tested"
  }, null, 2));
}
