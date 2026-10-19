from app.retrieval import search_documents

questions = [
    "高压线束进水需要检查吗？",
    "没有厂家授权可以拆解电池包吗？",
    "座椅加热失效应该如何维修？",
    "车机蓝牙无法连接如何处理？",
]

for question in questions:
    result = search_documents(question, top_k=1)[0]

    print(f"\n问题：{question}")
    print(f"来源：{result['source']}")
    print(f"距离：{result['distance']:.4f}")
    print(f"片段：{result['text']}")