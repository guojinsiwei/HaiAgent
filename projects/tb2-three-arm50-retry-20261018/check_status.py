import collections,json
import campaign,retry
retry.validate()
h=retry.read(retry.P/'health.json')
rows,skipped=retry.select_rows(h)
print(json.dumps(dict(parent_state=h.get('state'),parent_updated=h.get('updated_utc'),parent_summary=h.get('summary'),parent_active=len(h.get('active',[])),eligible=len(rows),eligible_by_arm=dict(collections.Counter(r['arm'] for r in rows)),skipped=skipped,schedule=retry.read(retry.R/'schedule.json')),ensure_ascii=False))
