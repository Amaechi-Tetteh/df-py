import time
import brownie
from enforce_typing import enforce_types
import pytest

from util import calcrewards, csvs, dispense, oceanutil, networkutil, query
from util.blockrange import BlockRange
from util.constants import BROWNIE_PROJECT as B
from util.oceanutil import OCEAN_address, OCEANtoken, recordDeployedContracts
from util import oceantestutil

accounts = None

@enforce_types
def test_without_csvs():
    chainID = networkutil.DEV_CHAINID

    st, fin, n = 1, len(chain), 25
    rng = BlockRange(st, fin, n)
    OCEAN_avail = 10000.0

    (_, S0, V0) = query.query_all(rng, chainID)
    rates = {"OCEAN": 0.5, "H2O": 1.618}

    stakes, poolvols = {chainID: S0}, {chainID: V0}
    rewards = calcrewards.calcRewards(stakes, poolvols, rates, OCEAN_avail)
    sum_ = sum(rewards[chainID].values())
    assert sum_ == pytest.approx(OCEAN_avail, 0.01), sum_


@enforce_types
def test_with_csvs(DEV_ADDRESS_FILE, tmp_path):
    """
    Simulate these steps, with csvs in between
    1. dftool query
    2. dftool getrate
    3. dftool calc
    4. dftool dispense
    """
    chainID = networkutil.DEV_CHAINID
    csv_dir = str(tmp_path)

    st, fin, n = 1, len(chain), 25
    rng = BlockRange(st, fin, n)
    token_addr = OCEAN_address()

    # 1. simulate "dftool query"
    (_, S0, V0) = query.query_all(rng, chainID)
    csvs.saveStakesCsv(S0, csv_dir, chainID)
    csvs.savePoolvolsCsv(V0, csv_dir, chainID)
    S0 = V0 = None  # ensure not used later

    # 2. simulate "dftool getrate"
    csvs.saveRateCsv("OCEAN", 0.25, csv_dir)
    csvs.saveRateCsv("H2O", 1.61, csv_dir)

    # 3. simulate dftool calc"
    S = csvs.loadStakesCsvs(csv_dir)
    V = csvs.loadPoolvolsCsvs(csv_dir)
    rates = csvs.loadRateCsvs(csv_dir)
    OCEAN_avail = 10000.0
    rewards = calcrewards.calcRewards(S, V, rates, OCEAN_avail)
    sum_ = sum(rewards[chainID].values())
    assert sum_ == pytest.approx(OCEAN_avail, 0.01), sum_
    csvs.saveRewardsCsv(rewards, csv_dir, "OCEAN")
    rewards = None  # ensure not used later

    # 4. simulate "dftool dispense"
    rewards = csvs.loadRewardsCsv(csv_dir, "OCEAN")
    dfrewards_addr = B.DFRewards.deploy({"from": accounts[0]}).address
    dispense.dispense(rewards[chainID], dfrewards_addr, token_addr, accounts[0])


@enforce_types
def setup_module():
    chainID = networkutil.DEV_CHAINID
    networkutil.connect(chainID)

    global accounts
    accounts = brownie.network.accounts
    address_file = networkutil.chainIdToAddressFile(chainID)
    oceanutil.recordDeployedContracts(address_file)
    oceantestutil.fillAccountsWithOCEAN()

    num_pools = 1
    oceantestutil.randomDeployTokensAndPoolsThenConsume(num_pools, OCEANtoken())
    time.sleep(2)


@enforce_types
def teardown_module():
    networkutil.disconnect()

