# SSHFerry 文档索引

<div align="center">
  <p>
    <img src="https://img.shields.io/badge/Docs-%E6%8C%81%E7%BB%AD%E7%BB%B4%E6%8A%A4-0F172A?style=for-the-badge" alt="持续维护文档">
    <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="后端文档">
    <img src="https://img.shields.io/badge/Frontend-React%20%2B%20Vite-2563EB?style=for-the-badge&logo=react&logoColor=white" alt="前端文档">
    <img src="https://img.shields.io/badge/Language-%E4%B8%AD%E6%96%87-111827?style=for-the-badge" alt="中文文档">
  </p>

  <p>
    面向当前 SSHFerry 代码库的实现级文档入口。
  </p>

  <p>
    <b>中文</b> |
    <a href="README.md">English</a>
  </p>

  <p>
    <a href="#文档地图">文档地图</a> |
    <a href="#推荐阅读路径">推荐阅读路径</a> |
    <a href="#范围规则">范围规则</a>
  </p>
</div>

## 文档地图

### 核心文档

- 🛠️ [后端总览](backend/BACKEND_OVERVIEW_zh.md)
- 📘 [前端构建指南](frontend/FRONTEND_BUILD_zh.md)
- 🔌 [前端接口指南](frontend/FRONTEND_API_zh.md)
- 🎨 [前端设计指南](frontend/FRONTEND_DESIGN_zh.md)

### 补充说明

- 🇨🇳 [传输规则对齐说明](backend/TRANSFER_RULES_zh.md)

## 推荐阅读路径

### 面向通用贡献者

1. 🧭 先看产品级入口 [README_zh.md](../README_zh.md)
2. 🛠️ 再读 [后端总览](backend/BACKEND_OVERVIEW_zh.md)
3. 🔌 只有在需要接口级细节时再进入前端 API 文档

### 面向前端开发

1. 📘 先读 [前端构建指南](frontend/FRONTEND_BUILD_zh.md)
2. 🔌 再看 [前端接口指南](frontend/FRONTEND_API_zh.md)
3. 🎨 最后读 [前端设计指南](frontend/FRONTEND_DESIGN_zh.md)

### 面向后端开发

1. 🛠️ 先读 [后端总览](backend/BACKEND_OVERVIEW_zh.md)
2. 🔍 再对照当前路由和服务代码核实行为
3. 🇨🇳 遇到协议或传输规则背景问题时，再看传输规则说明

## 这个目录怎么用

<table>
  <tr>
    <td width="33%" valign="top">
      <h3>🧭 先从入口页开始</h3>
      <p>根目录 README 用来说明项目定位、安装方式和推荐运行路径。</p>
    </td>
    <td width="33%" valign="top">
      <h3>🛠️ 这里放实现细节</h3>
      <p>`docs/` 主要承载架构、接口、构建和集成细节，避免把根 README 变成实现清单。</p>
    </td>
    <td width="33%" valign="top">
      <h3>🔍 代码优先</h3>
      <p>如果文档和当前实现不一致，在文档更新前应以代码库行为为准。</p>
    </td>
  </tr>
</table>

## 范围规则

- 📌 根目录 `README.md` 和 `README_zh.md` 是产品级入口文档。
- 📚 `docs/` 保存实现与协作导向的参考材料。
- 🔍 接口行为以当前后端代码为第一依据，这些文档是辅助说明。
- 🧹 历史草案、过时迁移说明和重复资源不会继续留在这里误导读者。

## 维护说明

- 新增、删除或重命名维护中的文档时，同步更新这个索引页。
- 优先链接到最合适的单篇文档，而不是在多个地方重复复制同一段说明。
- 如果某篇文档变成“规划口径”而不是“当前实现描述”，就应该收缩或重写。
