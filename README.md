# close-call-watch

Tracks the Close Call market from the referee's signed posts (price, longs and shorts, open interest, owners, top scores) and spends inference to read the stance of the trading-room chatter.

Counting is arithmetic; deciding what messages *are* is inference, and every call
is metered into `spend.jsonl`. Nothing is published unless `--publish` is passed.

```
python agent.py                 # measure, classify, print, publish nothing
python agent.py --publish       # ... and post the finding and the note
```

Inference auto-detects Ollama on localhost; set `AGENT_MODEL` to pick a model.
