import json
import pytest
from app import chatgpt_audio as audio, runtime as rt
from app.config import settings


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'runtime_path', str(tmp_path / 'runtime.sqlite3'))
    rt.init()
    ctx = audio.context('CASE-AF1D9C5F')
    record = audio.recordings(ctx)[0]
    (tmp_path / 'data').mkdir()
    mapping = {'url': audio.ORIGIN + '/recordings/test/' + record['filename'], 'sha256': record['sha256']}
    manifest = tmp_path / 'data/hosted_recordings.json'
    manifest.write_text(json.dumps({'recordings': {record['recording_id']: mapping}}))
    monkeypatch.setattr(audio, 'ROOT', tmp_path)
    return record, mapping, manifest


def test_playback_before_investigation_is_read_only_and_url_is_model_hidden(hosted):
    record, mapping, _ = hosted
    result = audio.recording_result('CASE-AF1D9C5F')
    assert result.structuredContent['inline_available'] is True
    assert result.structuredContent['transcript_status'] != 'available'
    assert result.meta['media_url'] == mapping['url']
    assert mapping['url'] not in result.content[0].text
    assert mapping['url'] not in json.dumps(result.structuredContent)
    with rt.db() as c:
        assert c.execute('SELECT count(*) FROM runs').fetchone()[0] == 0
        assert c.execute('SELECT count(*) FROM snapshots').fetchone()[0] == 0


@pytest.mark.parametrize('override', [
    {'url': 'http://trade-surveillance-demo-audio.vercel.app/clip.mp3'},
    {'url': 'https://trade-surveillance-demo-audio.vercel.app.evil.test/clip.mp3'},
    {'sha256': 'tampered'},
])
def test_untrusted_host_or_hash_falls_back_to_original(hosted, override):
    record, mapping, manifest = hosted
    manifest.write_text(json.dumps({'recordings': {record['recording_id']: mapping | override}}))
    result = audio.recording_result('CASE-AF1D9C5F')
    assert result.structuredContent['inline_available'] is False
    assert result.meta['media_url'] is None
    assert '/api/cases/CASE-AF1D9C5F/audio/' in result.structuredContent['original_recording_url']


def test_cross_case_recording_is_rejected(hosted):
    with pytest.raises(ValueError, match='permitted recording'):
        audio.recording_result('CASE-0088C625', hosted[0]['recording_id'])
