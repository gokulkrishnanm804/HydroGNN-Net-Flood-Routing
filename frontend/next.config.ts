/** @type {import('next').NextConfig} */
const nextConfig = {
  turbopack: {},
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'unpkg.com' },
    ],
  },
  async rewrites() {
    return [
      { source: '/basin-map', destination: '/map' },
      { source: '/flood-routing', destination: '/routing' },
      { source: '/data-pipeline', destination: '/pipeline' },
    ];
  },
};

module.exports = nextConfig;

