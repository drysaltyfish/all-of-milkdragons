import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// GitHub Pages 的「项目站点」会挂在 https://<user>.github.io/<repo>/ 这个子路径下，
// 所以生产构建的 base 必须是 /<repo>/。
// 以后如果绑了自定义域名（变成根路径站点），把环境变量 BASE_PATH 设为 / 即可。
const base = process.env.BASE_PATH || '/all-of-milkdragons/'

export default defineConfig({
  base,
  plugins: [vue()],
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    // 卡片墙是纯静态数据，不需要 sourcemap 上线
    sourcemap: false,
  },
})
