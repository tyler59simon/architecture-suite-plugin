// Accepts driver GPS pings and appends them to Bigtable.
const { Bigtable } = require('@google-cloud/bigtable');

exports.handlePing = async function handlePing(ping) {
  const client = new Bigtable();
  return client.instance('fleet-telemetry').table('pings').insert(ping);
};
