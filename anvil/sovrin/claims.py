'''
Full claims runner for demo purposes.

It is recommended to keep the actor names as steward, issuer, prover, & verifier (all lowercase).
User-facing names are implemented on the Fetch side.
Changing names means going through the modules (esp. issue.py & proofs.py) and dynamically naming fields
[actor]_key or [actor]_did depending on the context.
'''

import logging, argparse, sys, json, time, os

from ctypes import CDLL

from utilities import run_coroutine, send_data, receive_data, generate_nonce, generate_base58
from setup import setup_pool, set_self_up, teardown
from onboarding import demo_onboard
from schema import create_schema, create_credential_definition
from credentials import offer_credential, receive_credential_offer, request_credential, create_and_send_credential, store_credential
from proofs import request_proof_of_credential, create_proof_of_credential, verify_proof

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARN)

parser = argparse.ArgumentParser(description='Run python getting-started scenario (Prover/Issuer)')
parser.add_argument('-t', '--storage_type', help='load custom wallet storage plug-in')
parser.add_argument('-l', '--library', help='dynamic library to load for plug-in')
parser.add_argument('-e', '--entrypoint', help='entry point for dynamic library')
parser.add_argument('-c', '--config', help='entry point for dynamic library')
parser.add_argument('-s', '--creds', help='entry point for dynamic library')
args = parser.parse_known_args()[0]


# Check if we need to dyna-load a custom wallet storage plug-in
if args.storage_type:
    if not (args.library and args.entrypoint):
        parser.print_help()
        sys.exit(0)
    stg_lib = CDLL(args.library)
    result = stg_lib[args.entrypoint]()
    if result != 0:
        print('Error unable to load wallet storage', result)
        parser.print_help()
        sys.exit(0)

    print('Success, loaded wallet storage', args.storage_type)


async def run():

    cred_request, schema, proof_request, assertions_to_make, self_attested_attributes, \
    requested_attributes, requested_predicates, non_issuer_attributes \
    = load_example_data('../example_data/service_example/')

    # Add a nonce to the proof request and stringify
    proof_request['nonce'] = generate_nonce(25)

    # Requests need to be json formatted
    proof_request = json.dumps(proof_request)
    cred_request = json.dumps(cred_request)

    # Set up pool
    pool_name, pool_handle = await setup_pool('local')

    # Set up actors
    # For demo purposes, parameters ID, KEY are just random base58 strings here
    # Generally only seed-initialise Steward Anchors
    steward = await set_self_up('steward', generate_base58(64), generate_base58(64), pool_handle,
                                seed = '000000000000000000000000Steward1')
    issuer = await set_self_up('issuer', generate_base58(64), generate_base58(64), pool_handle)
    prover = await set_self_up('prover', generate_base58(64), generate_base58(64), pool_handle)
    verifier = await set_self_up('verifier', generate_base58(64), generate_base58(64), pool_handle)
    
    '''
    Onboard each actor with the parties they will interact with.
    Assuming no pre-existing relationships:
    1. Onboard the issuer and verifier with a steward.
    2. Onboard the prover with the issuer and verifier.
    '''
    steward, issuer = await demo_onboard(steward, issuer)
    steward, verifier = await demo_onboard(steward, verifier)
    issuer, prover = await demo_onboard(issuer, prover)
    verifier, prover = await demo_onboard(verifier, prover)
    
    # Create schema and corresponding definition
    unique_schema_name, schema_id, issuer = await create_schema(schema, issuer)
    issuer = await create_credential_definition(issuer, schema_id, unique_schema_name, revocable = False)

    # Issue credential
    issuer, cred_offer = await offer_credential(issuer, unique_schema_name)

    send_data(cred_offer)
    prover['authcrypted_cred_offer'] = receive_data()

    prover = await receive_credential_offer(prover)
    prover, cred_request = await request_credential(prover, cred_request)

    send_data(cred_request)
    issuer['authcrypted_cred_request'] = receive_data()

    issuer, cred = await create_and_send_credential(issuer)

    send_data(cred)
    prover['authcrypted_cred'] = receive_data()

    prover = await store_credential(prover)
    

    # Verify credential
    verifier, proof_request = await request_proof_of_credential(verifier, proof_request)

    send_data(proof_request)
    prover['authcrypted_proof_request'] = receive_data()

    prover, proof = await create_proof_of_credential(prover, self_attested_attributes, requested_attributes,
                                              requested_predicates, non_issuer_attributes)
    
    send_data(proof)
    verifier['authcrypted_proof'] = receive_data()

    verifier = await verify_proof(verifier, assertions_to_make)

    await teardown(pool_name, pool_handle, [steward, issuer, prover, verifier])

    print('Credential verified.')


# Loads examples in the example_data folder
def load_example_data(path):
    example_data = {}
    for filename in os.listdir(path):
        with open(path + filename) as file_:
            example_data[filename.replace('.json', '')] = json.load(file_)
    cred_request = example_data['credential_request']
    # Specify schema version
    schema = example_data['credential_schema']
    proof_request = example_data['proof_request']['request']
    assertions_to_make = example_data['proof_request']['assertions_to_make']
    # Don't json.dump this
    self_attested_attributes = example_data['proof_creation']['self_attested_attributes']
    requested_attributes = example_data['proof_creation']['requested_attributes']
    requested_predicates = example_data['proof_creation']['requested_predicates']
    non_issuer_attributes = example_data['proof_creation']['non_issuer_attributes']
    return cred_request, schema, proof_request, assertions_to_make, self_attested_attributes, \
           requested_attributes, requested_predicates, non_issuer_attributes


if __name__ == '__main__':
    run_coroutine(run)
    time.sleep(1)  # FIXME waiting for libindy thread complete
