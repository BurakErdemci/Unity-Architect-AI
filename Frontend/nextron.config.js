module.exports = {
  // Bu ayar Nextron'un ana süreci (main) yeniden başlatmasını engeller
  mainSrcDir: 'main',
  rendererSrcDir: 'renderer',
  
  // Webpack'e Backend klasörünü tamamen görmezden gelmesini söyleyelim
  webpack: (config, env) => {
    config.watchOptions = {
      ignored: [
        '**/Backend/**', 
        '**/node_modules/**', 
        '**/.next/**', 
        '**/*.db'
      ],
    };
    return config;
  },
};