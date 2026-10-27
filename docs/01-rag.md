# 1. What RAG is and why

**Retrieval-augmented generation** means: find the relevant passages first, then ask the model to answer using only those passages.

## Why not just ask the model?

- The model was not trained on your procedures.
- It will produce a fluent answer anyway. Fluent and wrong is the worst outcome in a safety context.
- You can't audit where the answer came from.

RAG fixes all three. The model becomes a reader and summarizer of your documents, which is the job it does well. That is the force-multiplier framing: the tool makes a skilled person faster, it does not replace their judgment.

## The pipeline in this repo

Read `app/rag.py`. It is about 40 lines:

1. **Authorize**: map the user to a role and allowed labels (`app/rbac.py`).
2. **Retrieve**: embed the question, search only chunks with allowed labels.
3. **Prompt**: number each chunk `[1]`, `[2]` and tell the model to cite them and to say "I don't know" when the context lacks the answer.
4. **Generate**: call the provider.
5. **Log**: record user, role, latency, tokens, and cost.

## Exercise

Run the app, sign in as `guest`, and ask "What is the firewall name for the ESP?" Then ask as `dev`. Explain why the answers differ, and in which step that happens.
