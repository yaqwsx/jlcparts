module.exports = {
  purge: [
    "./src/**/*.js",
    "./public/**.html"
  ],
  target: 'relaxed',
  prefix: '',
  important: false,
  separator: ':',
  theme: {
    fontFamily: {
      'sans': ['Lato', 'Arial', 'sans-serif'],
    },
    container: {
      screens: {
         sm: "100%",
         md: "100%",
         lg: "100%",
         xl: "1600px"
      }
    },
    minWidth: {
      '0': '0',
      '200': '200pt',
      'full': '100%',
    }
  },
  variants: {
    backgroundColor: ['responsive', 'odd', 'even', 'hover', 'focus'],
  },
  future: {
    removeDeprecatedGapUtilities: true,
    purgeLayersByDefault: true
  },
  corePlugins: {},
  plugins: [],
}
