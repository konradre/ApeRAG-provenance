## 致谢

本项目基于 [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) 进行深度改造和优化。我们对原作者的杰出工作表示衷心的感谢！

**原项目信息:**
- Repository: https://github.com/HKUDS/LightRAG
- Paper: "LightRAG: Simple and Fast Retrieval-Augmented Generation" (arXiv:2410.05779)
- Authors: Zirui Guo, Lianghao Xia, Yanhua Yu, Tu Ao, Chao Huang
- License: MIT License

## 为什么需要改造 LightRAG

尽管 LightRAG 提供了创新的图结构 RAG 方案，但在生产环境中我们遇到了以下挑战：

1. **并发限制**：原版设计为单实例串行处理，无法支持高并发场景
2. **全局状态依赖**：大量全局变量导致多实例相互影响
3. **任务队列集成困难**：与 Celery/Prefect 等异步任务队列集成时存在事件循环冲突
4. **存储实现冗余**：包含过多实验性存储，增加维护负担
5. **生产稳定性不足**：缺乏完善的错误处理和资源管理

## ApeRAG 的改进

经过深度重构，我们实现了以下改进：

### 🚀 核心架构重构

1. **完全无状态设计**
   - 删除了`shared_storage.py` 全局状态管理
   - 支持真正的多进程、多线程、多协程并发

2. **通用并发控制系统**
   - 开发了独立的 `concurrent_control` 模块
   - 支持多线程、多协程、多进程场景
   - 提供超时控制和灵活的锁管理

3. **生产级存储实现**
   - 删除了实验性代码和不必要的存储适配器
   - 专注于 PostgreSQL、Neo4j、Redis、Qdrant 等生产级存储

4. **任务队列完美集成**
   - 支持 Celery、Prefect 等所有主流任务队列

## 架构对比

### 原版 LightRAG
```
┌─────────────────┐
│  Global State   │ ← 所有实例共享
├─────────────────┤
│ Pipeline Status │ ← 全局互斥锁
├─────────────────┤
│   LightRAG      │ ← 单实例串行
└─────────────────┘
```

### ApeRAG 改进版
```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  LightRAG #1    │  │  LightRAG #2    │  │  LightRAG #N    │
│  (Stateless)    │  │  (Stateless)    │  │  (Stateless)    │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         ↓                    ↓                    ↓
┌─────────────────────────────────────────────────────────────┐
│              Concurrent Control Module                      │
└─────────────────────────────────────────────────────────────┘
         ↓                    ↓                    ↓
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   PostgreSQL    │  │     Neo4j       │  │    Redis        │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

## 开源协议

本项目的 LightRAG 部分遵循原项目的 MIT 协议。ApeRAG 的其他部分遵循 Apache 2.0 协议。

## 引用

如果你使用了我们的改进版本，请同时引用原论文和我们的项目：

**原始 LightRAG:**
```bibtex
@article{guo2024lightrag,
  title={LightRAG: Simple and Fast Retrieval-Augmented Generation},
  author={Zirui Guo and Lianghao Xia and Yanhua Yu and Tu Ao and Chao Huang},
  year={2024},
  eprint={2410.05779},
  archivePrefix={arXiv},
  primaryClass={cs.IR}
}
```

**ApeRAG 项目:**
```
ApeRAG Team. (2025). ApeRAG: Production-Ready RAG System. 
GitHub: https://github.com/apecloud/ApeRAG
```

## 更多信息

- 详细的改进日志：[CHANGELOG-zh.md](CHANGELOG-zh.md)
- 并发问题分析：[lightrag_concurrent_problems-zh.md](../lightrag_concurrent_problems-zh.md)
