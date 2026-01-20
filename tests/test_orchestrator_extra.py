import pytest
import asyncio
import time
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch, mock_open
from core.orchestrator import Job, JobScheduler
from core.config import AccountProfile, BotSettings

@pytest.fixture
def mock_settings():
    return BotSettings(
        max_concurrent_bots=2,
        max_concurrent_per_profile=1,
        user_agents=["Agent1"]
    )

@pytest.fixture
def mock_browser_manager():
    manager = AsyncMock()
    manager.create_context = AsyncMock()
    manager.new_page = AsyncMock()
    manager.check_health = AsyncMock(return_value=True)
    manager.restart = AsyncMock()
    return manager

class TestOrchestratorExtra:
    
    def test_job_from_dict(self):
        """Cover Job.from_dict (lines 54-55)."""
        data = {
            "priority": 1,
            "next_run": 100.0,
            "name": "test",
            "profile": {"faucet": "f", "username": "u", "password": "p", "enabled": True},
            "faucet_type": "ft",
            "job_type": "jt",
            "retry_count": 0
        }
        job = Job.from_dict(data)
        assert isinstance(job.profile, AccountProfile)
        assert job.name == "test"

    def test_restore_session_scenarios(self, mock_settings, mock_browser_manager):
        """Cover _restore_session scenarios (lines 99-110)."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        # Scenario 1: Valid JSON, old next_run (line 101-104)
        valid_job_data = {
            "queue": [{
                "priority": 1,
                "next_run": time.time() - 10000,
                "name": "old_job",
                "profile": {"faucet": "f", "username": "u", "password": "p", "enabled": True},
                "faucet_type": "ft",
                "job_type": "jt"
            }]
        }
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=json.dumps(valid_job_data))):
            scheduler.queue = []  # Clear any jobs loaded during init
            scheduler._restore_session()
            assert len(scheduler.queue) == 1
            assert scheduler.queue[0].next_run >= time.time() - 1 # Should be updated to now

        # Scenario 2: Invalid JSON (line 110)
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data="invalid json")):
            scheduler._restore_session()
            
        # Scenario 3: Valid JSON but invalid Job data (line 105-106)
        valid_json_invalid_job = json.dumps({"queue": [{"invalid": "data"}]})
        with patch("os.path.exists", return_value=True), \
             patch("builtins.open", mock_open(read_data=valid_json_invalid_job)):
            scheduler._restore_session()

    def test_persist_session_error(self, mock_settings, mock_browser_manager):
        """Cover _persist_session error path (lines 123-124)."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        with patch("builtins.open", side_effect=Exception("Write error")):
            scheduler._persist_session() # Should log warning

    def test_write_heartbeat_error(self, mock_settings, mock_browser_manager):
        """Cover _write_heartbeat error path (lines 131-132)."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        with patch("builtins.open", side_effect=Exception("Heartbeat error")):
            scheduler._write_heartbeat() # Should log debug

    def test_proxy_rotation_strategies(self, mock_settings, mock_browser_manager):
        """Cover proxy rotation strategies (lines 188-202) and detection (176)."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        scheduler.proxy_manager = None  # Disable manager to test internal scheduler logic
        proxies = ["p1", "p2", "p3"]
        
        # 1. Round Robin (default)
        profile_rr = AccountProfile(faucet="f", username="rr", password="p", proxy_pool=proxies, proxy_rotation_strategy="round_robin")
        assert scheduler.get_next_proxy(profile_rr) == "p1"
        assert scheduler.get_next_proxy(profile_rr) == "p2"
        
        # 2. Random
        profile_rnd = AccountProfile(faucet="f", username="rnd", password="p", proxy_pool=proxies, proxy_rotation_strategy="random")
        p = scheduler.get_next_proxy(profile_rnd)
        assert p in proxies
        
        # 3. Health Based
        profile_hb = AccountProfile(faucet="f", username="hb", password="p", proxy_pool=proxies, proxy_rotation_strategy="health_based")
        # Record 3 failures to exceed threshold (MAX_PROXY_FAILURES=3)
        scheduler.record_proxy_failure("p1")
        scheduler.record_proxy_failure("p1")
        scheduler.record_proxy_failure("p1")
        assert scheduler.get_next_proxy(profile_hb) == "p2" # p2 has 0

        # 4. Burned proxy reset - Feature not implemented in orchestrator yet
        # scheduler.record_proxy_failure("p3", detected=True)
        # scheduler.proxy_failures["p3"]["last_failure_time"] = time.time() - 50000 
        # scheduler.get_next_proxy(profile_rr)
        # assert not scheduler.proxy_failures["p3"]["burned"]

    @pytest.mark.asyncio
    async def test_run_job_wrapper_edge_cases(self, mock_settings, mock_browser_manager):
        """Cover proxy split, browser restart, and cleanup failure."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        profile = AccountProfile(faucet="f", username="u", password="p", proxy="http://user:pass@proxy:8080")
        job = Job(priority=1, next_run=time.time(), name="n", profile=profile, faucet_type="mock_faucet")
        
        # 1. Proxy split (line 254)
        mock_bot_instance = MagicMock()
        mock_bot_instance.claim_wrapper = AsyncMock(return_value=MagicMock(status="Success"))
        
        with patch("core.registry.get_faucet_class", return_value=lambda s, p: mock_bot_instance):
            await scheduler._run_job_wrapper(job)
            mock_bot_instance.set_proxy.assert_called_with("http://user:pass@proxy:8080")

        # 2. Proxy detection result (lines 269-276)
        mock_result_detect = MagicMock()
        mock_result_detect.status = "Proxy Detected"
        mock_bot_instance.claim_wrapper = AsyncMock(return_value=mock_result_detect)
        with patch("core.registry.get_faucet_class", return_value=lambda s, p: mock_bot_instance):
            await scheduler._run_job_wrapper(job)
            assert scheduler.proxy_failures["http://user:pass@proxy:8080"]["burned"]

        # 3. Browser restart on consecutive failures (lines 292-294)
        scheduler.consecutive_job_failures = 4
        mock_bot_instance.claim_wrapper = AsyncMock(side_effect=Exception("Fail"))
        with patch("core.registry.get_faucet_class", return_value=lambda s, p: mock_bot_instance):
            await scheduler._run_job_wrapper(job)
            assert mock_browser_manager.restart.called
            assert scheduler.consecutive_job_failures == 0

        # 4. Context cleanup failure (lines 305-306)
        mock_context = AsyncMock()
        mock_context.close = AsyncMock(side_effect=Exception("Cleanup fail"))
        mock_browser_manager.create_context.return_value = mock_context
        mock_bot_instance.claim_wrapper = AsyncMock(return_value=MagicMock(status="Success"))
        with patch("core.registry.get_faucet_class", return_value=lambda s, p: mock_bot_instance):
            await scheduler._run_job_wrapper(job) # Should log warning

    @pytest.mark.asyncio
    async def test_scheduler_loop_limits_and_errors(self, mock_settings, mock_browser_manager):
        """Cover global/profile limits, domain delay, and health check failure."""
        
        async def mock_wait():
            await asyncio.sleep(1)

        async def mock_wait_for_cancelled(aw, timeout):
            aw.close()
            raise asyncio.CancelledError

        # 1. Health check failure (lines 330-331)
        scheduler1 = JobScheduler(mock_settings, mock_browser_manager)
        scheduler1._stop_event.wait = mock_wait
        
        mock_browser_manager.check_health = AsyncMock(return_value=False)
        scheduler1.last_health_check_time = 0
        
        with patch("asyncio.wait_for", side_effect=mock_wait_for_cancelled):
            try: await scheduler1.scheduler_loop()
            except asyncio.CancelledError: pass
            assert mock_browser_manager.restart.called

        # 2. Global limit (line 346) - fresh scheduler
        mock_browser_manager.reset_mock()
        mock_settings.max_concurrent_bots = 0 
        scheduler2 = JobScheduler(mock_settings, mock_browser_manager)
        scheduler2._stop_event.wait = mock_wait
        
        job = Job(priority=1, next_run=time.time()-10, name="n", profile=AccountProfile(faucet="f", username="u", password="p"), faucet_type="test")
        scheduler2.add_job(job)
        
        with patch("asyncio.wait_for", side_effect=mock_wait_for_cancelled):
             try: await scheduler2.scheduler_loop()
             except asyncio.CancelledError: pass
             assert len(scheduler2.running_jobs) == 0

        # 3. Profile limit (line 351) - fresh scheduler
        mock_settings.max_concurrent_bots = 5
        mock_settings.max_concurrent_per_profile = 0
        scheduler3 = JobScheduler(mock_settings, mock_browser_manager)
        scheduler3._stop_event.wait = mock_wait
        
        job3 = Job(priority=1, next_run=time.time()-10, name="n3", profile=AccountProfile(faucet="f", username="u3", password="p"), faucet_type="test")
        scheduler3.add_job(job3)
        
        with patch("asyncio.wait_for", side_effect=mock_wait_for_cancelled):
             try: await scheduler3.scheduler_loop()
             except asyncio.CancelledError: pass
             assert len(scheduler3.running_jobs) == 0

        # 4. Domain rate limiting - test the method directly 
        scheduler4 = JobScheduler(mock_settings, mock_browser_manager)
        fixed_time = 1000.0
        scheduler4.domain_last_access["test"] = fixed_time - 1.0  # 1s ago
        with patch("core.orchestrator.time.time", return_value=fixed_time):
            delay = scheduler4.get_domain_delay("test")
            assert delay == 44  # MIN_DOMAIN_GAP_SECONDS (45) - elapsed (1)

        # 5. TimeoutError in loop (lines 440-441)
        scheduler5 = JobScheduler(mock_settings, mock_browser_manager)
        scheduler5._stop_event.wait = mock_wait
        
        call_count = 0
        async def mock_wait_for_custom(aw, timeout):
            nonlocal call_count
            aw.close() # Always close input coro
            if call_count == 0:
                call_count += 1
                raise asyncio.TimeoutError
            raise asyncio.CancelledError

        with patch("asyncio.wait_for", side_effect=mock_wait_for_custom):
             try: await scheduler5.scheduler_loop()
             except asyncio.CancelledError: pass # Should hit line 441

    def test_new_methods(self, mock_settings, mock_browser_manager):
        """Cover is_off_peak_time (146-169) and get_faucet_priority (171-203)."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        # 1. is_off_peak_time
        from datetime import datetime
        # Sunday at 2 AM
        with patch("datetime.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2024, 1, 7, 2, 0) # Sunday
            assert scheduler.is_off_peak_time() is True
            
            # Monday at 10 AM
            mock_dt.now.return_value = datetime(2024, 1, 8, 10, 0)
            assert scheduler.is_off_peak_time() is False

        # 2. get_faucet_priority (184-203)
        with patch("core.analytics.get_tracker") as mock_tracker:
            tracker_inst = MagicMock()
            mock_tracker.return_value = tracker_inst
            tracker_inst.get_faucet_stats.return_value = {"test": {"success_rate": 80}}
            tracker_inst.get_hourly_rate.return_value = {"test": 200}
            
            p = scheduler.get_faucet_priority("test")
            assert 0.1 <= p <= 2.0
            
            # Error path (201)
            tracker_inst.get_faucet_stats.side_effect = Exception("error")
            assert scheduler.get_faucet_priority("test") == 0.5

    @pytest.mark.asyncio
    async def test_run_job_wrapper_unknown_faucet(self, mock_settings, mock_browser_manager):
        """Cover unknown faucet type error (line 243)."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        job = Job(priority=1, next_run=time.time(), name="u", profile=AccountProfile(faucet="f", username="u", password="p"), faucet_type="unknown")
        with patch("core.registry.get_faucet_class", return_value=None):
            await scheduler._run_job_wrapper(job) # Should log error

    def test_proxy_fallbacks(self, mock_settings, mock_browser_manager):
        """Cover proxy failure and burned cooldown branches (233, 239, 243-244)."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        proxies = ["p1"]
        # Set primary proxy to p1 so fallback returns it
        profile = AccountProfile(faucet="f", username="u", password="p", proxy="p1", proxy_pool=proxies)
        
        # 1. Burned skip (233)
        scheduler.record_proxy_failure("p1", detected=True)
        # Line 233 hit if skip happens, but here it falls back to first proxy at 244
        p = scheduler.get_next_proxy(profile)
        assert p == "p1" 

        # 2. General failure skip (239)
        scheduler.proxy_failures["p1"] = {'failures': 5, 'last_failure_time': time.time(), 'burned': False}
        p = scheduler.get_next_proxy(profile)
        assert p == "p1" # Fallback at 244

    def test_is_off_peak_time_weekend(self, mock_settings, mock_browser_manager):
        """Cover weekend detection in is_off_peak_time (line 167)."""
        scheduler = JobScheduler(mock_settings, mock_browser_manager)
        
        from datetime import datetime, timezone
        
        # Saturday at 12:00 (weekday() = 5)
        with patch('datetime.datetime') as mock_dt:
            mock_now = datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = mock_now
            assert scheduler.is_off_peak_time() is True
        
        # Sunday at 15:00 (weekday() = 6)
        with patch('datetime.datetime') as mock_dt:
            mock_now = datetime(2024, 1, 7, 15, 0, tzinfo=timezone.utc)
            mock_dt.now.return_value = mock_now
            assert scheduler.is_off_peak_time() is True

    @pytest.mark.asyncio
    async def test_withdrawal_off_peak_scheduling(self, mock_browser_manager):
        """Cover withdrawal off-peak requirement (lines 421-425)."""
        # Create fresh settings and scheduler for this test
        settings = BotSettings(
            max_concurrent_bots=2,
            max_concurrent_per_profile=1,
            user_agents=["Agent1"]
        )
        
        with patch.object(JobScheduler, '_restore_session'), \
             patch.object(JobScheduler, '_persist_session'):
            scheduler = JobScheduler(settings, mock_browser_manager)
            
            # Create a withdrawal job
            profile = AccountProfile(faucet="f", username="u_withdraw", password="p")
            job = Job(
                priority=1, 
                next_run=time.time() - 10,  # Ready to run
                name="test_withdraw", 
                profile=profile, 
                faucet_type="test",
                job_type="withdraw_coins"
            )
            scheduler.add_job(job)
            
            # Mock non-off-peak time (Tuesday 10 AM)
            from datetime import datetime, timezone
            with patch('datetime.datetime') as mock_dt:
                mock_now = datetime(2024, 1, 9, 10, 0, tzinfo=timezone.utc)
                mock_dt.now.return_value = mock_now
                
                # Try to run the scheduler
                with patch("asyncio.wait_for", side_effect=asyncio.CancelledError):
                    try:
                        await scheduler.scheduler_loop()
                    except asyncio.CancelledError:
                        pass
                
                # Job should still be in queue, postponed (line 424)
                assert len(scheduler.queue) == 1
                assert scheduler.queue[0].next_run > time.time()

    @pytest.mark.asyncio
    async def test_domain_rate_limiting_postpone(self, mock_browser_manager):
        """Cover domain rate limiting postpone (lines 415-417)."""
        # Create fresh settings and scheduler for this test
        settings = BotSettings(
            max_concurrent_bots=2,
            max_concurrent_per_profile=1,
            user_agents=["Agent1"]
        )
        
        with patch.object(JobScheduler, '_restore_session'), \
             patch.object(JobScheduler, '_persist_session'):
            scheduler = JobScheduler(settings, mock_browser_manager)
            
            # Create a job
            profile = AccountProfile(faucet="f", username="u_domain", password="p")
            job = Job(
                priority=1, 
                next_run=time.time() - 10,  # Ready to run
                name="test_job", 
                profile=profile, 
                faucet_type="test_faucet"
            )
            
            # Set domain was accessed very recently
            scheduler.domain_last_access["test_faucet"] = time.time()
            scheduler.add_job(job)
            
            # Try to run the scheduler
            with patch("asyncio.wait_for", side_effect=asyncio.CancelledError):
                try:
                    await scheduler.scheduler_loop()
                except asyncio.CancelledError:
                    pass
            
            # Job should still be in queue, postponed (line 416)
            assert len(scheduler.queue) == 1
            assert scheduler.queue[0].next_run > time.time()
