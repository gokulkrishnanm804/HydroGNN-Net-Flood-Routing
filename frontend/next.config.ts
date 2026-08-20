/** @type {import('next').NextConfig} */
const nextConfig = {
  turbopack: {},
  images: {
    remotePatterns: [
      { protocol: 'https', hostname: 'unpkg.com' },
    ],
  },
};

module.exports = nextConfig;

