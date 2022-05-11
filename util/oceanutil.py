from collections import namedtuple
from enforce_typing import enforce_types
import hashlib
import json
from typing import Any, List, Dict, Tuple

import brownie

from util.base18 import toBase18
from util.constants import BROWNIE_PROJECT as B, ZERO_ADDRESS

CONTRACTS = {}


@enforce_types
def _contracts(key: str):
    global CONTRACTS
    return CONTRACTS[key]


@enforce_types
def recordDeployedContracts(address_file: str, network: str):
    global CONTRACTS
    C = CONTRACTS
    if C != {}:  # already filled
        return

    with open(address_file, "r") as json_file:
        a = json.load(json_file)[network]  # dict of contract_name: address

    C["Ocean"] = B.Simpletoken.at(a["Ocean"])
    C["ERC721Template"] = B.ERC721Template.at(a["ERC721Template"]["1"])
    C["ERC20Template"] = B.ERC20Template.at(a["ERC20Template"]["1"])
    C["PoolTemplate"] = B.BPool.at(a["poolTemplate"])
    C["Router"] = B.FactoryRouter.at(a["Router"])
    C["Staking"] = B.SideStaking.at(a["Staking"])
    C["ERC721Factory"] = B.ERC721Factory.at(a["ERC721Factory"])


def OCEANtoken():
    return _contracts("Ocean")


def OCEAN_address() -> str:
    return OCEANtoken().address


def ERC721Template():
    return _contracts("ERC721Template")


def ERC20Template():
    return _contracts("ERC20Template")


def PoolTemplate():
    return _contracts("PoolTemplate")


def factoryRouter():
    return _contracts("Router")


def Staking():
    return _contracts("Staking")


def ERC721Factory():
    return _contracts("ERC721Factory")


@enforce_types
def createDataNFT(name: str, symbol: str, from_account):
    erc721_factory = ERC721Factory()
    template_index = 1
    additional_metadata_updater = ZERO_ADDRESS
    additional_erc20_deployer = factoryRouter().address
    transferable = True
    owner = from_account.address
    token_uri = "https://mystorage.com/mytoken.png"
    
    tx = erc721_factory.deployERC721Contract(
        name,
        symbol,
        template_index,
        additional_metadata_updater,
        additional_erc20_deployer,
        token_uri,
        transferable,
        owner,
        {"from": from_account},
    )
    data_NFT_address = tx.events["NFTCreated"]["newTokenAddress"]
    data_NFT = B.ERC721Template.at(data_NFT_address)
    return data_NFT


@enforce_types
def createDatatokenFromDataNFT(
    DT_name: str, DT_symbol: str, data_NFT, from_account
):

    erc20_template_index = 1
    strings = [
        DT_name,
        DT_symbol,
    ]
    addresses = [
        from_account.address,  # minter
        from_account.address,  # fee mgr
        from_account.address,  # pub mkt
        ZERO_ADDRESS,  # pub mkt fee token addr
    ]
    uints = [
        toBase18(1.0),  # cap. Note contract will hardcod this to max_int
        toBase18(0.0),  # pub mkt fee amt
    ]
    _bytes: List[Any] = []

    tx = data_NFT.createERC20(
        erc20_template_index, strings, addresses, uints, _bytes, {"from": from_account}
    )
    DT_address = tx.events["TokenCreated"]["newTokenAddress"]
    DT = B.ERC20Template.at(DT_address)

    return DT


@enforce_types
def createBPoolFromDatatoken(
    datatoken,
    erc721_factory,
    from_account,
    init_OCEAN_liquidity: float = 2000.0,
    DT_OCEAN_rate: float = 0.1,
    DT_vest_amt: float = 1000.0,
    DT_vest_num_blocks: int = 2426000,  # min allowed=2426000, see FactoryRouter.sol
    LP_swap_fee: float = 0.03,
    mkt_swap_fee: float = 0.01,
):  # pylint: disable=too-many-arguments

    OCEAN = OCEANtoken()
    pool_template = PoolTemplate()
    router = factoryRouter()  # router.routerOwner() = '0xe2DD..' = accounts[0]
    ssbot = Staking()

    OCEAN.approve(
        router.address, toBase18(init_OCEAN_liquidity), {"from": from_account}
    )

    ss_params = [
        toBase18(DT_OCEAN_rate),
        OCEAN.decimals(),
        toBase18(DT_vest_amt),
        DT_vest_num_blocks,  # do _not_ convert to wei
        toBase18(init_OCEAN_liquidity),
    ]
    swap_fees = [
        toBase18(LP_swap_fee),
        toBase18(mkt_swap_fee),
    ]
    addresses = [
        ssbot.address,
        OCEAN.address,
        from_account.address,
        from_account.address,
        from_account.address,
        pool_template.address,
    ]

    tx = datatoken.deployPool(ss_params, swap_fees, addresses, {"from": from_account})
    pool_address = _poolAddressFromNewBPoolTx(tx)
    pool = B.BPool.at(pool_address)

    return pool


@enforce_types
def _poolAddressFromNewBPoolTx(tx) -> str:
    return tx.events["NewPool"]["poolAddress"]


# ===============================================================================
# fee stuff needed for consume

# follow order in ocean.py/ocean_lib/structures/abi_tuples.py::ConsumeFees
@enforce_types
def get_zero_consume_mkt_fee_tuple() -> Tuple:
    d = {
        "consumeMarketFeeAddress": ZERO_ADDRESS,
        "consumeMarketFeeToken": ZERO_ADDRESS,
        "consumeMarketFeeAmount": 0,
    }

    consume_mkt_fee = (
        d["consumeMarketFeeAddress"],
        d["consumeMarketFeeToken"],
        d["consumeMarketFeeAmount"],
    )
    return consume_mkt_fee


# follow order in ocean.py/ocean_lib/structures/abi_tuples.py::ProviderFees
@enforce_types
def get_zero_provider_fee_tuple(pub_account) -> Tuple:
    d = get_zero_provider_fee_dict(pub_account)

    provider_fee = (
        d["providerFeeAddress"],
        d["providerFeeToken"],
        d["providerFeeAmount"],
        d["v"],
        d["r"],
        d["s"],
        d["validUntil"],
        d["providerData"],
    )

    return provider_fee


# from ocean.py/tests/resources/helper_functions.py
@enforce_types
def get_zero_provider_fee_dict(provider_account) -> Dict[str, Any]:
    web3 = brownie.web3
    provider_fee_amount = 0
    compute_env = None
    provider_data = json.dumps({"environment": compute_env}, separators=(",", ":"))
    provider_fee_address = provider_account.address
    provider_fee_token = ZERO_ADDRESS
    valid_until = 0

    message = web3.solidityKeccak(
        ["bytes", "address", "address", "uint256", "uint256"],
        [
            web3.toHex(web3.toBytes(text=provider_data)),
            provider_fee_address,
            provider_fee_token,
            provider_fee_amount,
            valid_until,
        ],
    )
    signed = web3.eth.sign(provider_fee_address, data=message)
    signature = split_signature(signed)

    provider_fee = {
        "providerFeeAddress": provider_fee_address,
        "providerFeeToken": provider_fee_token,
        "providerFeeAmount": provider_fee_amount,
        "providerData": web3.toHex(web3.toBytes(text=provider_data)),
        # make it compatible with last openzepellin https://github.com/OpenZeppelin/openzeppelin-contracts/pull/1622
        "v": signature.v,
        "r": signature.r,
        "s": signature.s,
        "validUntil": 0,
    }

    return provider_fee


# from ocean.py/ocean_lib/web3_internal/utils.py
Signature = namedtuple("Signature", ("v", "r", "s"))

# from ocean.py/ocean_lib/web3_internal/utils.py
@enforce_types
def split_signature(signature: Any) -> Signature:
    """
    :param signature: signed message hash, hex str
    """
    web3 = brownie.web3
    assert len(signature) == 65, (
        f"invalid signature, " f"expecting bytes of length 65, got {len(signature)}"
    )
    v = web3.toInt(signature[-1])
    r = to_32byte_hex(int.from_bytes(signature[:32], "big"))
    s = to_32byte_hex(int.from_bytes(signature[32:64], "big"))
    if v != 27 and v != 28:
        v = 27 + v % 2

    return Signature(v, r, s)


# from ocean.py/ocean_lib/web3_internal/utils.py
@enforce_types
def to_32byte_hex(val: int) -> str:
    """

    :param val:
    :return:
    """
    web3 = brownie.web3
    return web3.toHex(web3.toBytes(val).rjust(32, b"\0"))


@enforce_types
def calcDID(nft_addr: str) -> str:
    nft_addr2 = brownie.web3.toChecksumAddress(nft_addr)
    chain_id = brownie.network.chain.id  # in base10

    # adapted from ocean.py/ocean_lib/ocean/ocean_assets.py
    did = f"did:op:{create_checksum(nft_addr2 + str(chain_id))}"
    return did


# from ocean.py/ocean_lib/utils/utilities.py
@enforce_types
def create_checksum(text: str) -> str:
    """
    :return: str
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
