import path from "path"
import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"
import sourceIdentifierPlugin from 'vite-plugin-source-identifier'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiBaseUrl = env.VITE_API_BASE_URL
  const proxyTarget =
    env.VITE_API_PROXY_TARGET ||
    (apiBaseUrl?.startsWith('http') ? apiBaseUrl.replace(/\/api\/?$/, '') : undefined) ||
    'http://127.0.0.1:8080'

  return {
    plugins: [
      react(),
      sourceIdentifierPlugin({
        enabled: mode !== 'production',
        attributePrefix: 'data-matrix',
        includeProps: true,
      })
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "./src"),
      },
    },
    server: {
      proxy: {
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes('node_modules')) {
              return undefined
            }
            if (id.includes('reactflow') || id.includes('@reactflow')) {
              return 'vendor-flow'
            }
            if (id.includes('d3-')) {
              return 'vendor-d3'
            }
            if (id.includes('recharts')) {
              return 'vendor-recharts'
            }
            if (id.includes('framer-motion')) {
              return 'vendor-motion'
            }
            if (id.includes('lucide-react')) {
              return 'vendor-icons'
            }
            return undefined
          },
        },
      },
    },
  }
})
