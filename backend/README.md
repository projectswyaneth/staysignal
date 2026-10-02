# StaySignal scoring API

The console runs the model in the browser so a judge can see it work with no
server at all. In production the model belongs behind an API **inside Hutch's
network**, and this is that service.

```bash
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
open http://localhost:8000/docs
```

| Endpoint | Purpose |
|---|---|
| `GET /health` | Is the service up, which model is loaded, and what reference state it holds |
| `GET /model` | The full model card — every weight, published on purpose |
| `POST /score` | Score one customer and explain the score |
| `POST /score/batch` | Score up to 10,000 at once — the realistic call |

## What a request carries, and what it does not

Three of the model's feature families are not properties of a customer at all:

| Not in the request | Because it belongs to | Loaded from |
|---|---|---|
| Population baseline | the whole base, that week | the nightly job |
| Cell condition | the network | OSS / NMS |
| Market pressure | a district | the market feed |

So a request carries only what is genuinely about the customer: their static
record and their weekly history (at least 17 weeks — fewer, and they have no
baseline window of their own and are not scored).

That split is also what keeps scores reproducible. If a caller could supply the
population baseline, a caller could change it, and no score in the system would
be auditable afterwards.

## Two things it refuses to do

- **Score a customer whose serving cell is unknown.** Treating an unseen tower as
  a healthy one is the silent failure that matters most, so it is an error
  rather than a default.
- **Score a customer with too little history.** They are excluded and counted,
  never guessed at.

The model file is produced by `ml/train.py`, and feature building imports
`ml/features.py` directly — never a re-implementation.
