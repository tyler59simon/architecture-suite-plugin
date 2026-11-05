'use strict';
const ELK = require('./assets/elk.bundled.js');
let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => {
  input += chunk;
  if (input.length > 20000000) { process.stderr.write('Graph exceeds 20 MB'); process.exit(3); }
});
process.stdin.on('end', async () => {
  try { process.stdout.write(JSON.stringify(await new ELK().layout(JSON.parse(input)))); }
  catch (error) { process.stderr.write(String(error)); process.exitCode = 2; }
});
