import { restoreCheckpoint } from '../src/checkpoints.mjs';
const [root, snapshot, preserved] = process.argv.slice(2);
if (!root || !snapshot || !preserved) throw new Error('explicit root, snapshot and preservation directory required');
console.log(JSON.stringify(await restoreCheckpoint(root,snapshot,preserved)));
