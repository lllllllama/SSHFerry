# SSHFerry Docs

这个目录用于放项目的分类文档，根目录只保留仓库入口文档。

## Structure

- `frontend/`
  - React 前端开发、联调、构建、交互设计和接口对接文档
- `backend/`
  - FastAPI 后端迁移、规划和实现说明
- `architecture/`
  - 架构说明、历史设计稿和参考性文档

## Current Docs

- [Frontend Build Guide](./frontend/FRONTEND_BUILD.md)
- [Frontend API Guide](./frontend/FRONTEND_API.md)
- [Frontend Design Specification](./frontend/Frontend-Design.md)
- [Backend TODO](./backend/BACKEND_TODO.md)
- [Historical Architecture Note](./architecture/agent.md)

## Frontend Reading Order

建议前端开发按这个顺序读：

1. [Frontend Build Guide](./frontend/FRONTEND_BUILD.md)
2. [Frontend API Guide](./frontend/FRONTEND_API.md)
3. [Frontend Design Specification](./frontend/Frontend-Design.md)

这样可以先确认工程约束，再确认接口契约，最后落具体交互和页面语义。

## Notes

- 仓库根目录保留 [README.md](../README.md) 和 `README_zh.md` 作为总入口。
- [docs/architecture/agent.md](./architecture/agent.md) 是历史设计文档，内容和当前实现可能不完全一致，阅读时以现有代码与最新迁移文档为准。
