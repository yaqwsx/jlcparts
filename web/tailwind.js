module.exports = {
  purge: [],
  target: 'relaxed',
  prefix: '',
  important: false,
  separator: ':',
  theme: {
    container: {
      screens: {
         sm: "100%",
         md: "100%",
         lg: "100%",
         xl: "1600px"
      }
    }
  },
  future: {
    removeDeprecatedGapUtilities: true,
    purgeLayersByDefault: true
  },
  corePlugins: {},
  plugins: [],
}
