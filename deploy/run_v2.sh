#!/usr/bin/env bash
# Chain the protocol-v2 runs unattended on the server: for each graph variant, restart the brain on it, wait until it is
# live, start the protocol, wait for it to finish, stop (flushes logs). Body must be in dry run and the stimulus screen
# in place. usage: sudo bash deploy/run_v2.sh   (logs → /home/ommatid/ommatid/logs/<variant>/, run log → run_v2.log)
set -u
cd /home/ommatid/ommatid
TOKEN=$(grep OMMATID_TOKEN .env | cut -d= -f2)
VARIANTS="${VARIANTS:-graph.npz graph_shuffled.npz graph_shuffled_2027.npz graph_shuffled_2028.npz graph_scrambled.npz graph_clamped.npz}"
NOTE="${NOTE:-v2 run, laptop 30 cm @ 40 cm in front of the camera, body dry-run}"
log(){ echo "$(date -u +%FT%TZ) $*" | tee -a run_v2.log; }
for g in $VARIANTS; do
  log "=== $g"
  sed -i "s#^OMMATID_GRAPH=.*#OMMATID_GRAPH=/home/ommatid/ommatid/build/$g#" .env
  systemctl restart ommatid-brain
  for i in $(seq 1 90); do curl -s -m 2 http://127.0.0.1:8700/health | grep -q '"seen": "live"' && break; sleep 3; done
  sleep 30
  curl -s http://127.0.0.1:8700/state.json | python3 -c "import sys,json; s=json.load(sys.stdin); print('variant', s.get('graph_variant'), 'graph', s.get('graph_sha'), 'columns', s.get('columns_sha'), 'hz_per_unit', s.get('hz_per_unit'), 'seen', s.get('seen'))" | tee -a run_v2.log
  curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"trials_per_condition\": 30, \"seed\": 2026, \"note\": \"$NOTE; graph $g\"}" http://127.0.0.1:8700/protocol/start >/dev/null
  until curl -s -m 5 http://127.0.0.1:8700/protocol/status.json | grep -q '"finished": true'; do sleep 30; done
  curl -s -X POST -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8700/protocol/stop | tee -a run_v2.log; echo | tee -a run_v2.log
  log "=== done $g"
done
sed -i "s#^OMMATID_GRAPH=.*#OMMATID_GRAPH=/home/ommatid/ommatid/build/graph.npz#" .env
systemctl restart ommatid-brain
log "all runs done; brain back on the original graph"
