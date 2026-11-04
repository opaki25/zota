import type { NextConfig } from 'next';
// Service bindings are runtime-only. API forwarding lives in app/api, not here.
const config: NextConfig = { output: 'standalone' };
export default config;
