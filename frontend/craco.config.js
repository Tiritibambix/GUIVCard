module.exports = {
  style: {
    postcss: {
      plugins: [
        require('tailwindcss'),
        require('autoprefixer'),
      ],
    },
  },
  webpack: {
    configure: {
      ignoreWarnings: [
        {
          module: /node_modules/,
        },
      ],
    },
  },
};