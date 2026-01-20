import json
import os

session_file = 'config/session_state.json'
if os.path.exists(session_file):
    with open(session_file, 'r') as f:
        data = json.load(f)
    
    queue = data.get('queue', [])
    seen = set()
    new_queue = []
    
    for job in queue:
        username = job['profile']['username']
        faucet = job['faucet_type']
        job_type = job['job_type']
        key = f"{username}:{faucet}:{job_type}"
        
        if key not in seen and faucet.lower() != 'test':
            seen.add(key)
            new_queue.append(job)
    
    removed = len(queue) - len(new_queue)
    data['queue'] = new_queue
    
    with open(session_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Successfully cleaned up {removed} duplicate or test jobs.")
else:
    print("❌ session_state.json not found.")
