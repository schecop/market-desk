// n8n exports a list with instance-specific fields (timestamps, version ids, the owner project).
// Keep only what defines the workflow, so the file diffs cleanly and imports on any instance.
// Usage (inside the n8n container): node clean-export.js <exported.json> <output.json>
const fs = require('fs');

const [input, output] = process.argv.slice(2);
const [workflow] = JSON.parse(fs.readFileSync(input, 'utf8'));
const { id, name, nodes, connections, settings } = workflow;
const clean = { id, name, active: false, nodes, connections, settings };
fs.writeFileSync(output, JSON.stringify(clean, null, 2) + '\n');
