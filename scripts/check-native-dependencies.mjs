import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const lock = JSON.parse(readFileSync(new URL('../package-lock.json', import.meta.url), 'utf8'));
const parents = Object.entries(lock.packages).filter(([path]) =>
  /(?:^|\/)node_modules\/(?:lightningcss|@tailwindcss\/oxide)$/.test(path),
);
assert.equal(parents.length, 2, 'Expected Lightning CSS and Tailwind Oxide in the lockfile');

// Check every declared platform, not just the OS generating the lockfile.
for (const [path, parent] of parents) {
  for (const [name, version] of Object.entries(parent.optionalDependencies || {})) {
    const candidates = [path + '/node_modules/' + name, 'node_modules/' + name];
    const dependency = candidates.map(key => lock.packages[key]).find(Boolean);
    assert.ok(dependency, `Lockfile is missing native package ${name}`);
    assert.equal(dependency.version, version, `Native version mismatch: ${name}`);
    assert.ok(dependency.resolved && dependency.integrity, `Missing registry metadata: ${name}`);
  }
}
console.log('All Lightning CSS and Tailwind Oxide platform packages are locked.');

if (!process.argv.includes('--lock-only')) {
  const webRequire = createRequire(new URL('../apps/web/package.json', import.meta.url));
  const postcssRequire = createRequire(webRequire.resolve('@tailwindcss/postcss'));
  const tailwindRequire = createRequire(postcssRequire.resolve('@tailwindcss/node'));
  const lightning = tailwindRequire('lightningcss');
  const result = lightning.transform({
    filename: 'native-smoke.css',
    code: Buffer.from('.native-smoke { color: red; }'),
    minify: true,
  });
  assert.ok(result.code.length > 0, 'Lightning CSS must transform CSS');
  const oxide = postcssRequire('@tailwindcss/oxide');
  assert.equal(typeof oxide.Scanner, 'function', 'Tailwind Oxide native scanner must load');
  console.log(`Native CSS modules load and execute on ${process.platform}/${process.arch}.`);
}
