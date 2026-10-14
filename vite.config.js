import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 站点已经绑了自定义域名 www.宇宙奶龙大全.space（punycode: www.xn--15qr2q0gp9eucq780c.space），
// 自定义域名下站点挂在**根路径**，所以 base 默认是 '/'。
//
// ⚠️ 如果哪天去掉自定义域名、回到 GitHub Pages 的「项目站点」，
//    站点会变成挂在 https://<user>.github.io/<repo>/ 子路径下，
//    那时必须用 BASE_PATH=/<repo>/ 构建，否则 assets / fonts / logos 全部 404，页面白屏：
//        BASE_PATH=/all-of-milkdragons/ npm run build
const base = process.env.BASE_PATH || '/'

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
