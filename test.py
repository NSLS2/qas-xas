from tiled.client import from_uri
from databroker import Broker

from xas.process import process_interpolate_bin_from_uid, process_interpolate_bin_with_tiled
# from xas.tiled_io import load_interpolated_df_from_tiled


# test uid provided by Lu Ma on Februrary 18
#uid = "187caec7-f260-4b10-8e0e-ed43e538afc2"    # fly_energy_scan_apb
uid = "ae446a58-bb9c-4ff8-8675-30c6e7067131"    # fly_energy_scan_xs3x
#uid = "76ed1151-7036-4eb2-a5b1-ae2d406eefaa" #Test Lightshow Demo

# Create tiled client objects
client = from_uri("https://tiled.nsls2.bnl.gov")
# qas_raw = client["qas/migration"]

# Wrap tiled client for QAS raw data in the databroker
# backward-compatible wrapper.
# db = Broker(qas_raw)


def test():
    # TEST WRITING
    "Load raw data, align columns by interpolating and binning, and save the result."
    # process_interpolate_bin_from_uid(uid, db)

    print(client.context)
    process_interpolate_bin_with_tiled(client[f"qas/raw/{uid}"], client["tst/sandbox/qas/processed"])

    # TEST READING
    # "Read the processed data back from tiled with the method isstools uses"
    # (a, b) = load_interpolated_df_from_tiled("foil Se-K 0001-r0002.raw")
    # print(a)
    # print(b)


if __name__ == "__main__":
    test()
