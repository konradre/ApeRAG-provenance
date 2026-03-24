## Acknowledgments

This project is based on [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) with extensive modifications and optimizations. We sincerely thank the original authors for their excellent work!

**Original Project:**
- Repository: https://github.com/HKUDS/LightRAG
- Paper: "LightRAG: Simple and Fast Retrieval-Augmented Generation" (arXiv:2410.05779)
- Authors: Zirui Guo, Lianghao Xia, Yanhua Yu, Tu Ao, Chao Huang
- License: MIT License

## Why We Modified LightRAG

Although LightRAG provides an innovative graph-structured RAG solution, we encountered the following challenges in production environments:

1. **Concurrency Limitations**: The original design processes a single instance serially, unable to support high-concurrency scenarios
2. **Global State Dependencies**: Numerous global variables cause interference between multiple instances
3. **Task Queue Integration Difficulties**: Event loop conflicts when integrating with async task queues like Celery/Prefect
4. **Storage Implementation Redundancy**: Contains too many experimental storage options, increasing maintenance burden
5. **Insufficient Production Stability**: Lacks comprehensive error handling and resource management

## Our Improvements

Through deep refactoring, we've implemented the following improvements:

### 🚀 Core Architecture Refactoring

1. **Completely Stateless Design**
   - Removed `shared_storage.py` global state management
   - Supports true multi-process, multi-thread, multi-coroutine concurrency

2. **Universal Concurrency Control System**
   - Developed independent `concurrent_control` module
   - Supports multi-thread, multi-coroutine, multi-process scenarios
   - Provides timeout control and flexible lock management

3. **Production-Grade Storage Implementation**
   - Removed experimental code and unnecessary storage adapters
   - Focused on production-grade storage like PostgreSQL, Neo4j, Redis, and Qdrant

4. **Perfect Task Queue Integration**
   - Supports all mainstream task queues including Celery and Prefect

## Architecture Comparison

### Original LightRAG
```
┌─────────────────┐
│  Global State   │ ← Shared across all instances
├─────────────────┤
│ Pipeline Status │ ← Global mutex lock
├─────────────────┤
│   LightRAG      │ ← Single instance serial processing
└─────────────────┘
```

### Improved ApeRAG
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

## License

The LightRAG portion of this project follows the original MIT License. Other parts of ApeRAG follow the Apache 2.0 License.

## Citations

If you use our improved version, please cite both the original paper and our project:

**Original LightRAG:**
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

**ApeRAG Project:**
```
ApeRAG Team. (2025). ApeRAG: Production-Ready RAG System. 
GitHub: https://github.com/apecloud/ApeRAG
```

## More Information

- Detailed improvement log: [CHANGELOG.md](CHANGELOG.md)
- Concurrency problem analysis: [lightrag_concurrent_problems.md](../lightrag_concurrent_problems.md)
