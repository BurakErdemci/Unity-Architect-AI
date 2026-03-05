const path = require('path');

module.exports = {
    webpack: (config, env) => {
        if (env === 'development') {
            config.watchOptions = {
                // Compile sonrası 3 saniye boyunca yeni değişiklikleri yok say
                aggregateTimeout: 3000,
                // Output klasörünü (app/) izleme — feedback loop'u önler
                ignored: [
                    path.join(process.cwd(), 'app'),
                    path.join(process.cwd(), '.next'),
                    path.join(process.cwd(), 'node_modules'),
                    path.join(process.cwd(), 'renderer'),
                ],
            };
        }
        return config;
    },
};
