import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const names = ['dsh', 'dsh-tools', 'dsh-system-prompt', 'dsh-agent-loop', 'dsh-scope', 'dsh-jobs', 'dsh-jobs-local', 'dsh-tool-bash', 'dsh-tool-jobs'];
for (const name of names) {
  let filename = require.resolve(`@deepseek-ai/${name}/package.json`);
  const data = JSON.parse(readFileSync(filename, 'utf8'));
  if (data.version !== '0.2.0-rc.2') throw new Error(`Host mismatch: ${name}@${data.version}`);
  console.log(`${name}@${data.version}`);
}
console.log('Pinned package versions match. This is NOT model/API acceptance.');
