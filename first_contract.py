from algosdk.v2client import algod
from algosdk.future.transaction import AssetConfigTxn, wait_for_confirmation
from algosdk.mnemonic import to_private_key
from algosdk import account, mnemonic
import json
from pyteal import *
import os

#   Utility function used to print created asset for account and assetid
def print_created_asset(algodclient, account, assetid):    
    # note: if you have an indexer instance available it is easier to just use this
    # response = myindexer.accounts(asset_id = assetid)
    # then use 'account_info['created-assets'][0] to get info on the created asset
    account_info = algodclient.account_info(account)
    idx = 0
    for my_account_info in account_info['created-assets']:
        scrutinized_asset = account_info['created-assets'][idx]
        idx = idx + 1       
        if (scrutinized_asset['index'] == assetid):
            print("Asset ID: {}".format(scrutinized_asset['index']))
            print(json.dumps(my_account_info['params'], indent=4))
            break

#   Utility function used to print asset holding for account and assetid
def print_asset_holding(algodclient, account, assetid):
    # note: if you have an indexer instance available it is easier to just use this
    # response = myindexer.accounts(asset_id = assetid)
    # then loop thru the accounts returned and match the account you are looking for
    account_info = algodclient.account_info(account)
    idx = 0
    for my_account_info in account_info['assets']:
        scrutinized_asset = account_info['assets'][idx]
        idx = idx + 1        
        if (scrutinized_asset['asset-id'] == assetid):
            print("Asset ID: {}".format(scrutinized_asset['asset-id']))
            print(json.dumps(scrutinized_asset, indent=4))
            break

def create_asa(asset_creator_address, passphrase):
    print("********************* Create ASA ********************************")
    algod_address = "https://testnet-api.algonode.cloud"
    algod_client = algod.AlgodClient("", algod_address)

    # asset_creator_address = ""
    # passphrase = ""

    private_key = to_private_key(passphrase)

    txn = AssetConfigTxn(
        sender=asset_creator_address,
        sp=algod_client.suggested_params(),
        total=1000,
        default_frozen=False,
        unit_name="ENB",
        asset_name="ENB",
        manager=asset_creator_address,
        reserve=asset_creator_address,
        freeze=asset_creator_address,
        clawback=asset_creator_address,
        url="https://path/to/my/asset/details", 
        decimals=0)
    # Sign with secret key of creator
    stxn = txn.sign(private_key)

    # Send the transaction to the network and retrieve the txid.
    try:
        txid = algod_client.send_transaction(stxn)
        print("Signed transaction with txID: {}".format(txid))
        # Wait for the transaction to be confirmed
        confirmed_txn = wait_for_confirmation(algod_client, txid, 4)  
        print("TXID: ", txid)
        print("Result confirmed in round: {}".format(confirmed_txn['confirmed-round']))   
    except Exception as err:
        print(err)
    # Retrieve the asset ID of the newly created asset by first
    # ensuring that the creation transaction was confirmed,
    # then grabbing the asset id from the transaction.
    print("Transaction information: {}".format(
        json.dumps(confirmed_txn, indent=4)))
    # print("Decoded note: {}".format(base64.b64decode(
    #     confirmed_txn["txn"]["txn"]["note"]).decode()))
    try:
        # Pull account info for the creator
        # account_info = algod_client.account_info(accounts[1]['pk'])
        # get asset_id from tx
        # Get the new asset's information from the creator account
        ptx = algod_client.pending_transaction_info(txid)
        asset_id = ptx["asset-index"]
        print_created_asset(algod_client, accounts[1]['pk'], asset_id)
        print_asset_holding(algod_client, accounts[1]['pk'], asset_id)
    except Exception as e:
        print(e)    

    return asset_id






def approval_program(asset_id):
    print("********************* Deploy the smart Contract ********************************")
    print("********************* Store ASA ID in global state ********************************")
    on_creation = Seq(
        [
            App.globalPut(Bytes("Creator"), Txn.sender()),
            Assert(Txn.application_args.length() == Int(4)),
            App.globalPut(Bytes("RegBegin"), Btoi(Txn.application_args[0])),
            App.globalPut(Bytes("RegEnd"), Btoi(Txn.application_args[1])),
            App.globalPut(Bytes("VoteBegin"), Btoi(Txn.application_args[2])),
            App.globalPut(Bytes("VoteEnd"), Btoi(Txn.application_args[3])),
            App.globalPut(Bytes("asaID"), Int(asset_id)),
            Return(Int(1)),
        ]
    )

    print("********************* Build upon the Voting app ********************************")

    #is the sender the address that created the application
    is_creator = Txn.sender() == App.globalGet(Bytes("Creator"))
    #localGetEx returns a maybe value. Exist or does not. Different from localGet.
    get_vote_of_sender = App.localGetEx(Int(0), Int(0), Bytes("voted"))

    asset_id_py = App.globalGet(Bytes("asaID"))
    asset_balance = AssetHolding.balance(Int(0), asset_id_py) 

    on_closeout = Seq(
        [
            get_vote_of_sender,asset_balance,
            If(
                And(
                    Global.round() <= App.globalGet(Bytes("VoteEnd")),
                    get_vote_of_sender.hasValue(),
                ),
                App.globalPut(
                    get_vote_of_sender.value(),
                    App.globalGet(get_vote_of_sender.value()) - asset_balance.value(),
                ),
            ),
            Return(Int(1)),
        ]
    )

    #this a clean way to define >=
    on_register = Return(
        And(
            Global.round() >= App.globalGet(Bytes("RegBegin")), 
            Global.round() <= App.globalGet(Bytes("RegEnd")),
        )
    )

    choice = Txn.application_args[1]
    choice_tally = App.globalGet(choice) 
    #choice_tally is number of votes of choice a or choice b or choice c
    #think of it as key and value pairs where choice is the key

    #asset_balance= AssetHolding.balance(Int(0), asset_id_py)
    on_vote = Seq(
        [
            Assert(
                And(
                    Global.round() >= App.globalGet(Bytes("VoteBegin")),
                    Global.round() <= App.globalGet(Bytes("VoteEnd")),
                )
            ),
            get_vote_of_sender, asset_balance,
            If(get_vote_of_sender.hasValue(), Return(Int(0))),
            If(asset_balance.value() < Int(1000),Return(Int(0))),
            If(choice != Bytes("yes") and choice != Bytes("no") and choice != Bytes("abstain"), Return(Int(0))),
            App.globalPut(choice, choice_tally + Int(1)),
            App.localPut(Int(0), Bytes("voted"), choice),
            Return(Int(1)),
        ]
    )

    program = Cond(
        [Txn.application_id() == Int(0), on_creation], #deploy application
        [Txn.on_completion() == OnComplete.DeleteApplication, Return(is_creator)], #this is how to check what type of application
        [Txn.on_completion() == OnComplete.UpdateApplication, Return(is_creator)],
        [Txn.on_completion() == OnComplete.CloseOut, on_closeout],
        [Txn.on_completion() == OnComplete.OptIn, on_register],
        [Txn.application_args[0] == Bytes("vote"), on_vote],
    )

    return program


def clear_state_program():
    get_vote_of_sender = App.localGetEx(Int(0), Int(0), Bytes("voted"))
    asset_id_py = App.globalGet(Bytes("asaID"))
    asset_balance = AssetHolding.balance(Int(0), asset_id_py) 

    program = Seq(
        [
            get_vote_of_sender, asset_balance,
            If(
                And(
                    Global.round() <= App.globalGet(Bytes("VoteEnd")),
                    get_vote_of_sender.hasValue(),
                ),
                App.globalPut(
                    get_vote_of_sender.value(),
                    App.globalGet(get_vote_of_sender.value()) - asset_balance.value(),
                ),
            ),
            Return(Int(1)),
        ]
    )

    return program


if __name__ == "__main__":

    mnemonic0=os.environ['mnemonic1']
    account0= os.environ['account1']

    #these steps are for printing out results
    accounts = {}
    counter = 1
    accounts[counter] = {}
    accounts[counter]['pk'] = mnemonic.to_public_key(mnemonic0)
    accounts[counter]['sk'] = mnemonic.to_private_key(mnemonic0)

    # 1. Create ASA 
    asset_id =create_asa(account0,mnemonic0)

    # 2. Run voting
    with open("vote_approval.teal", "w") as f:
        compiled = compileTeal(approval_program(asset_id), Mode.Application, version=6)
        f.write(compiled)

    with open("vote_clear_state.teal", "w") as f:
        compiled = compileTeal(clear_state_program(), Mode.Application, version=6)
        f.write(compiled)







