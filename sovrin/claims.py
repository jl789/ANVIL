import time

from indy import anoncreds, crypto, did, ledger, pool, wallet

import json
import logging

import argparse
import sys
from ctypes import *

from indy.error import ErrorCode, IndyError

from sovrin_utilities import get_pool_genesis_txn_path, run_coroutine

from config import PROTOCOL_VERSION



from setup import setup_pool, setup_steward
from onboarding import simple_onboard, onboard_for_proving, onboarding
from schema import * # Schema to use in this file
from credentials import create_schema, create_credential_definition
from issue import offer_credential, receive_credential_offer, request_credential, create_and_send_credential, store_credential





'''
v OPTIONS v
'''
# Wallet IDs and keys are currently mocked
# NOTE always pass keys as environment variables

POOL_NAME = 'ANVIL'

STEWARD_NAME = 'Sovrin Steward'
STEWARD_WALLET_ID = 'steward_wallet_id' 
STEWARD_WALLET_KEY = 'steward_wallet_key'
# Local pool setup demands this exact seed
STEWARD_SEED = '000000000000000000000000Steward1'

PROVER_NAME = 'Prover'
PROVER_WALLET_ID = 'prover_wallet_id'
PROVER_WALLET_KEY = 'prover_wallet_key'

ISSUER_NAME = 'Issuer'
ISSUER_WALLET_ID = 'issuer_wallet_id'
ISSUER_WALLET_KEY = 'issuer_wallet_key'

VERIFIER_NAME = 'Verifier'
VERIFIER_WALLET_ID = 'verifier_wallet_id'
VERIFIER_WALLET_KEY = 'verifier_wallet_key'
'''
^ OPTIONS ^
'''




logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARN)

parser = argparse.ArgumentParser(description='Run python getting-started scenario (Prover/Issuer)')
parser.add_argument('-t', '--storage_type', help='load custom wallet storage plug-in')
parser.add_argument('-l', '--library', help='dynamic library to load for plug-in')
parser.add_argument('-e', '--entrypoint', help='entry point for dynamic library')
parser.add_argument('-c', '--config', help='entry point for dynamic library')
parser.add_argument('-s', '--creds', help='entry point for dynamic library')

args = parser.parse_args()


# check if we need to dyna-load a custom wallet storage plug-in
if args.storage_type:
    if not (args.library and args.entrypoint):
        parser.print_help()
        sys.exit(0)
    stg_lib = CDLL(args.library)
    result = stg_lib[args.entrypoint]()
    if result != 0:
        print("Error unable to load wallet storage", result)
        parser.print_help()
        sys.exit(0)

    print("Success, loaded wallet storage", args.storage_type)


async def run():


    pool_ = await setup_pool('ANVIL')

    steward = await setup_steward(pool_ = pool_,
                                  name = 'Steward',
                                  id_ = 'mocked_steward_id',
                                  key = 'mocked_steward_key',
                                  seed = '000000000000000000000000Steward1')

    issuer, steward = await simple_onboard(pool_ = pool_,
                                           anchor = steward,
                                           name = 'issuer',
                                           id_ = 'mocked_issuer_id',
                                           key = 'mocked_issuer_key')

    prover, issuer = await onboard_for_proving(pool_ = pool_,
                                               anchor = issuer,
                                               name = 'prover',
                                               id_ = 'mocked_prover_id',
                                               key = 'mocked_prover_key')

    verifier, steward = await simple_onboard(pool_ = pool_,
                                             anchor = steward,
                                             name = 'verifier',
                                             id_ = 'mocked_verifier_id',
                                             key = 'mocked_verifier_key')
    
    

    # Create schema and corresponding definition
    schema = degree # Define type (NOTE MAKE OPTION VAR)
    unique_schema_name, schema_id, issuer = await create_schema(schema, issuer)
    issuer = await create_credential_definition(creator = issuer,
                                                schema_id = schema_id,
                                                unique_schema_name = unique_schema_name,
                                                revocable = False)


    # Specify values of credential request
    values = json.dumps({
        "first_name": {"raw": "Prover", "encoded": "1139481716457488690172217916278103335"},
        "last_name": {"raw": "SecondName", "encoded": "5321642780241790123587902456789123452"},
        "degree": {"raw": "Bachelor of Science, Marketing", "encoded": "12434523576212321"},
        "status": {"raw": "graduated", "encoded": "2213454313412354"},
        "ssn": {"raw": "123-45-6789", "encoded": "3124141231422543541"},
        "year": {"raw": "2015", "encoded": "2015"},
        "average": {"raw": "5", "encoded": "5"}
    })



    issuer, prover = await offer_credential(issuer, prover, unique_schema_name)
    prover = await receive_credential_offer(prover, unique_schema_name)
    prover, issuer = await request_credential(prover, issuer, values, unique_schema_name)
    issuer, prover = await create_and_send_credential(issuer, prover, unique_schema_name)
    prover = await store_credential(prover, unique_schema_name)




    print('Verifier requesting proof of credential...')
    # Prover onboarded with verifier
    verifier['did_for_prover'], verifier['key_for_prover'], prover['did_for_verifier'], prover['key_for_verifier'], \
    verifier['prover_connection_response'] = await onboarding(verifier, prover)
    # Create proof request
    verifier['job_application_proof_request'] = json.dumps({
        'nonce': '1432422343242122312411212',
        'name': 'Job-Application',
        'version': '0.1',
        'requested_attributes': {
            'attr1_referent': {
                'name': 'first_name'
            },
            'attr2_referent': {
                'name': 'last_name'
            },
            'attr3_referent': {
                'name': 'degree',
                'restrictions': [{'cred_def_id': issuer[unique_schema_name + '_cred_def_id']}]
            },
            'attr4_referent': {
                'name': 'status',
                'restrictions': [{'cred_def_id': issuer[unique_schema_name + '_cred_def_id']}]
            },
            'attr5_referent': {
                'name': 'ssn',
                'restrictions': [{'cred_def_id': issuer[unique_schema_name + '_cred_def_id']}]
            },
            'attr6_referent': {
                'name': 'phone_number'
            }
        },
        'requested_predicates': {
            'predicate1_referent': {
                'name': 'average',
                'p_type': '>=',
                'p_value': 4,
                'restrictions': [{'cred_def_id': issuer[unique_schema_name + '_cred_def_id']}]
            }
        }
    })
    # Get key for prover DID
    verifier['prover_key_for_verifier'] = \
        await did.key_for_did(verifier['pool'], verifier['wallet'], verifier['prover_connection_response']['did'])
    # Authenticate, encrypt and send
    verifier['authcrypted_job_application_proof_request'] = \
        await crypto.auth_crypt(verifier['wallet'], verifier['key_for_prover'], verifier['prover_key_for_verifier'],
                                verifier['job_application_proof_request'].encode('utf-8'))
    prover['authcrypted_job_application_proof_request'] = verifier['authcrypted_job_application_proof_request']


    print('Prover getting credential and creating proof...')
    # Decrypt
    prover['verifier_key_for_prover'], prover['job_application_proof_request'], _ = \
        await auth_decrypt(prover['wallet'], prover['key_for_verifier'], prover['authcrypted_job_application_proof_request'])
    # Search for a proof request and get the credential attributes needed
    search_for_job_application_proof_request = \
        await anoncreds.prover_search_credentials_for_proof_req(prover['wallet'],
                                                                prover['job_application_proof_request'], None)
    cred_for_attr1 = await get_credential_for_referent(search_for_job_application_proof_request, 'attr1_referent')
    cred_for_attr2 = await get_credential_for_referent(search_for_job_application_proof_request, 'attr2_referent')
    cred_for_attr3 = await get_credential_for_referent(search_for_job_application_proof_request, 'attr3_referent')
    cred_for_attr4 = await get_credential_for_referent(search_for_job_application_proof_request, 'attr4_referent')
    cred_for_attr5 = await get_credential_for_referent(search_for_job_application_proof_request, 'attr5_referent')
    cred_for_predicate1 = await get_credential_for_referent(search_for_job_application_proof_request, 'predicate1_referent')
    await anoncreds.prover_close_credentials_search_for_proof_req(search_for_job_application_proof_request)
    # Put the needed attributes in Indy-readable format
    prover['creds_for_job_application_proof'] = {cred_for_attr1['referent']: cred_for_attr1,
                                                cred_for_attr2['referent']: cred_for_attr2,
                                                cred_for_attr3['referent']: cred_for_attr3,
                                                cred_for_attr4['referent']: cred_for_attr4,
                                                cred_for_attr5['referent']: cred_for_attr5,
                                                cred_for_predicate1['referent']: cred_for_predicate1}
    # Get attributes from ledger
    prover['schemas'], prover['cred_defs'], prover['revoc_states'] = \
        await prover_get_entities_from_ledger(prover['pool'], prover['did_for_verifier'],
                                              prover['creds_for_job_application_proof'], prover['name'])
    # Create the proof, specifiying what to reveal (all are verifiable, though here for ex. personal info stays hidden)
    prover['job_application_requested_creds'] = json.dumps({
        'self_attested_attributes': {
            'attr1_referent': 'Prover',
            'attr2_referent': 'SecondName',
            'attr6_referent': '123-45-6789'
        },
        'requested_attributes': {
            'attr3_referent': {'cred_id': cred_for_attr3['referent'], 'revealed': True},
            'attr4_referent': {'cred_id': cred_for_attr4['referent'], 'revealed': True},
            'attr5_referent': {'cred_id': cred_for_attr5['referent'], 'revealed': True},
        },
        'requested_predicates': {'predicate1_referent': {'cred_id': cred_for_predicate1['referent']}}
    })
    prover['job_application_proof'] = \
        await anoncreds.prover_create_proof(prover['wallet'], prover['job_application_proof_request'],
                                            prover['job_application_requested_creds'], prover['master_secret_id'],
                                            prover['schemas'], prover['cred_defs'], prover['revoc_states'])
    # Authenticate, encrypt and send
    prover['authcrypted_job_application_proof'] = \
        await crypto.auth_crypt(prover['wallet'], prover['key_for_verifier'], prover['verifier_key_for_prover'],
                                prover['job_application_proof'].encode('utf-8'))
    verifier['authcrypted_job_application_proof'] = prover['authcrypted_job_application_proof']


    print('Verifier getting proof and verifying credential...')
    # Decrypt
    _, verifier['job_application_proof'], decrypted_job_application_proof = \
        await auth_decrypt(verifier['wallet'], verifier['key_for_prover'], verifier['authcrypted_job_application_proof'])
    # Get credential attribute values from ledger
    verifier['schemas'], verifier['cred_defs'], verifier['revoc_ref_defs'], verifier['revoc_regs'] = \
        await verifier_get_entities_from_ledger(verifier['pool'], verifier['did'],
                                                decrypted_job_application_proof['identifiers'], verifier['name'])
    # Assert everything is as claimed by the prover and verify
    assert 'Bachelor of Science, Marketing' == \
           decrypted_job_application_proof['requested_proof']['revealed_attrs']['attr3_referent']['raw']
    assert 'graduated' == \
           decrypted_job_application_proof['requested_proof']['revealed_attrs']['attr4_referent']['raw']
    assert '123-45-6789' == \
           decrypted_job_application_proof['requested_proof']['revealed_attrs']['attr5_referent']['raw']

    assert 'Prover' == decrypted_job_application_proof['requested_proof']['self_attested_attrs']['attr1_referent']
    assert 'SecondName' == decrypted_job_application_proof['requested_proof']['self_attested_attrs']['attr2_referent']
    assert '123-45-6789' == decrypted_job_application_proof['requested_proof']['self_attested_attrs']['attr6_referent']
    assert await anoncreds.verifier_verify_proof(verifier['job_application_proof_request'], verifier['job_application_proof'],
                                                 verifier['schemas'], verifier['cred_defs'], verifier['revoc_ref_defs'],
                                                 verifier['revoc_regs'])

    print('Credential verified.')
    print(steward.keys())
    print(issuer.keys())
    print(prover.keys())
    print(verifier.keys())




async def get_schema(pool_handle, _did, schema_id):
    get_schema_request = await ledger.build_get_schema_request(_did, schema_id)
    get_schema_response = await ledger.submit_request(pool_handle, get_schema_request)
    return await ledger.parse_get_schema_response(get_schema_response)




async def get_cred_def(pool_handle, _did, cred_def_id):
    get_cred_def_request = await ledger.build_get_cred_def_request(_did, cred_def_id)
    get_cred_def_response = await ledger.submit_request(pool_handle, get_cred_def_request)
    return await ledger.parse_get_cred_def_response(get_cred_def_response)


async def get_credential_for_referent(search_handle, referent):
    credentials = json.loads(
        await anoncreds.prover_fetch_credentials_for_proof_req(search_handle, referent, 10))
    return credentials[0]['cred_info']


async def prover_get_entities_from_ledger(pool_handle, _did, identifiers, actor):
    schemas = {}
    cred_defs = {}
    rev_states = {}
    for item in identifiers.values():
        logger.info("\"{}\" -> Get Schema from Ledger".format(actor))
        (received_schema_id, received_schema) = await get_schema(pool_handle, _did, item['schema_id'])
        schemas[received_schema_id] = json.loads(received_schema)

        logger.info("\"{}\" -> Get Claim Definition from Ledger".format(actor))
        (received_cred_def_id, received_cred_def) = await get_cred_def(pool_handle, _did, item['cred_def_id'])
        cred_defs[received_cred_def_id] = json.loads(received_cred_def)

        if 'rev_reg_seq_no' in item:
            pass  # TODO Create Revocation States

    return json.dumps(schemas), json.dumps(cred_defs), json.dumps(rev_states)


async def verifier_get_entities_from_ledger(pool_handle, _did, identifiers, actor):
    schemas = {}
    cred_defs = {}
    rev_reg_defs = {}
    rev_regs = {}
    for item in identifiers:
        logger.info("\"{}\" -> Get Schema from Ledger".format(actor))
        (received_schema_id, received_schema) = await get_schema(pool_handle, _did, item['schema_id'])
        schemas[received_schema_id] = json.loads(received_schema)

        logger.info("\"{}\" -> Get Claim Definition from Ledger".format(actor))
        (received_cred_def_id, received_cred_def) = await get_cred_def(pool_handle, _did, item['cred_def_id'])
        cred_defs[received_cred_def_id] = json.loads(received_cred_def)

        if 'rev_reg_seq_no' in item:
            pass  # TODO Get Revocation Definitions and Revocation Registries

    return json.dumps(schemas), json.dumps(cred_defs), json.dumps(rev_reg_defs), json.dumps(rev_regs)


async def auth_decrypt(wallet_handle, key, message):
    from_verkey, decrypted_message_json = await crypto.auth_decrypt(wallet_handle, key, message)
    decrypted_message_json = decrypted_message_json.decode("utf-8")
    decrypted_message = json.loads(decrypted_message_json)
    return from_verkey, decrypted_message_json, decrypted_message


if __name__ == '__main__':
    run_coroutine(run)
    time.sleep(1)  # FIXME waiting for libindy thread complete