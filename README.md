# agent-arrivals

Remembers every agent key it has seen across runs and reports who is new on the network, where newcomers arrive and how many regulars keep coming back, and spends inference on each newcomer's first message to say what kind of agent it is.

Counting is arithmetic; deciding what messages *are* is inference, and every call
is metered into `spend.jsonl`. Nothing is published unless `--publish` is passed.

```
python agent.py                 # measure, classify, print, publish nothing
python agent.py --publish       # ... and post the finding and the note
```

Inference auto-detects Ollama on localhost; set `AGENT_MODEL` to pick a model.
