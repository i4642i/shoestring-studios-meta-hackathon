"""Local OpenAI-shaped embeddings shim (stdlib server + MiniLM on CPU).

Exposes POST /v1/embeddings {input, model?} -> {data:[{embedding,...}]} so
graphrag can use local embeddings via api_base. Model downloads once (~90MB).
Run:  python scripts/embed_server.py [--port 8001]
"""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_model = None


def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print("loading %s ..." % MODEL_NAME, flush=True)
        _model = SentenceTransformer(MODEL_NAME)
        print("ready (%d dims)" % _model.get_sentence_embedding_dimension(),
              flush=True)
    return _model


class Handler(BaseHTTPRequestHandler):
    server_version = "EmbedShim/1"

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/v1/embeddings":
            return self._json(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode())
        except ValueError:
            return self._json(400, {"error": "need JSON body"})
        texts = body.get("input", "")
        if isinstance(texts, str):
            texts = [texts]
        vecs = get_model().encode(texts).tolist()
        return self._json(200, {
            "object": "list",
            "data": [{"object": "embedding", "index": i, "embedding": v}
                     for i, v in enumerate(vecs)],
            "model": body.get("model", MODEL_NAME),
        })

    def _json(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print("embeddings at http://localhost:%d/v1/embeddings" % args.port,
          flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
