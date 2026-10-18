import json

from chronos.discovery import live_probe
from chronos.risk.harvestable import transfers


def test_linuxone_openssl_35_peer_temp_key_output():
    from chronos.verify.checks import negotiated
    output='Protocol version: TLSv1.3\nVerification: OK\nPeer Temp Key: X25519, 253 bits\nDONE\n'
    assert live_probe.parse_s_client(output)=={'group':'X25519','protocol':'TLSv1.3'}
    assert negotiated(output)=='X25519'


def test_concurrent_store_writes_publish_complete_values(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from chronos.common import store
    monkeypatch.setattr(store,'ROOT',tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i:store.put('findings',{'writer':i,'rows':list(range(100))}),range(32)))
    assert store.get('findings')['rows']==list(range(100))
    assert not list((tmp_path/'store').glob('*.tmp'))


def test_extensionless_pem_ssh_host_key_is_discovered(demo_tree):
    from chronos.discovery import certs_keys
    root, _ = demo_tree
    source = next(root.rglob('*.pem'))
    # Fixture PEM includes both a certificate and private key.
    target = root / 'ssh_host_rsa_key'
    target.write_bytes(source.read_bytes())
    found = certs_keys.scan(root, root)
    assert any(a['path'] == 'ssh_host_rsa_key' and a['asset_type'] == 'related-crypto-material' for a in found)


def test_pinned_client_channel_is_not_misrepresented_by_server_probe():
    calls=[]
    topo={'channels':[{'id':'lab->partner','dst':'partner-lab','protocol':'tls','port':8443,'probe':False}]}
    assert live_probe.scan(topo,lambda command:calls.append(command)) == []
    assert calls == []


def test_actual_record_counts_win_over_variable_response_bytes():
    events=[{'request_uri':'/api/patients/export?limit=100','status':200,'ssl_curve':'X25519','bytes_sent':9999,'record_count':'100'},
            {'request_uri':'/api/patients/1','status':404,'ssl_curve':'X25519','bytes_sent':9999,'record_count':'0'},
            {'request_uri':'/api/patients/1','status':200,'ssl_curve':'X25519MLKEM768','bytes_sent':9999,'record_count':'1'}]
    result=transfers([json.dumps(e) for e in events],{'patients':500})['patients']
    assert result['R']==100
    assert result['sessions']=={'classical':2,'hybrid':1,'pq':0}
    assert not result.get('R_is_estimated',False)


def test_r_includes_actual_outbound_lab_copies(tmp_path, monkeypatch):
    from chronos.risk.service import already_sent
    for service,uri,count in [('portal','/api/labs/1',5),('partner-lab','/ingest?trace=x',1)]:
        folder=tmp_path/service; folder.mkdir()
        (folder/'chronos.log').write_text(json.dumps({'request_uri':uri,'status':200,'ssl_curve':'X25519','record_count':str(count)})+'\n')
    monkeypatch.setenv('CHRONOS_NGINX_LOG',str(tmp_path/'*'/'chronos.log'))
    assert already_sent({'tables':{'lab_results':{'mean_record_bytes':200}}},{'lab_results'})['lab_results']['R']==6
