from time import sleep

from .bin import rebin
from .rebinning import rebin as issrebin
from .file_io import (
    load_dataset_from_files,
    create_file_header,
    create_file_header_tiled,
    validate_file_exists,
    validate_path_exists,
    save_interpolated_df_as_file,
    save_binned_df_as_file,
    find_e0,
    save_binned_df_as_hdf5_file,
)

from xas.db_io import (
    load_apb_dataset_from_db,
    load_apb_dataset_from_tiled,
    load_apb_trig_dataset_from_tiled,
    load_xs3_dataset_from_tiled,
    load_xs3x_dataset_from_tiled,
    translate_apb_dataset,
    load_apb_trig_dataset_from_db,
    load_xs3_dataset_from_db,
    load_xs3_dataset_from_db_new,
    load_xs3x_dataset_from_db,
)
from .interpolate import interpolate, interpolate_with_interp

from .xas_logger import get_logger
from .xs3 import load_data_with_xs3

from datetime import datetime
from xas.metadata import generate_xdi_metadata
from tiled.client import from_uri
import pyarrow
import os
from pathlib import Path



def clean_dict(raw_dict):
    clean_raw_dict = {}
    for key in raw_dict.keys():
        df = raw_dict[key]
        zero_idx = df[df["timestamp"] == 0].index.min()
        if zero_idx is None:
            clean_raw_dict[key] = df
        else:
            clean_raw_dict[key] = df.loc[: zero_idx - 1]
    return clean_raw_dict


def average_roi_channels(dataframe=None):
    if dataframe is not None:
        # col1 = dataframe.columns.tolist()[:-1]
        for j in range(1, 5):
            dat = 0
            for i in range(1, 5):
                dat += getattr(dataframe, "CHAN" + str(i) + "ROI" + str(j))
            dataframe.insert(j + 4, column="ROI" + str(j) + "AVG", value=dat / 4)
            # col1.append('ROI' + str(j) + 'AVG')
        # col1.append('energy')
        # dataframe = dataframe[col1]
        print("Done with averaging")
    return dataframe


def average_roi_channels_xs3x(dataframe=None):
    if dataframe is not None:
        # col1 = dataframe.columns.tolist()[:-1]
        for j in range(1, 5):
            dat = 0
            for i in [1, 3, 4, 5, 6, 7, 8]:
                dat += getattr(dataframe, "CHAN" + str(i) + "ROI" + str(j))
            dataframe.insert(j + 4, column="ROI" + str(j) + "AVG", value=dat / 4)
            # col1.append('ROI' + str(j) + 'AVG')
        # col1.append('energy')
        # dataframe = dataframe[col1]
        print("Done with averaging")
    return dataframe


def process_interpolate_bin_from_uid(uid, db, e0=None):
    logger = get_logger()
    hdr = db[uid]
    experiment = hdr.start["experiment"]
    if experiment.startswith("fly"):
        path_to_file = hdr.start["interp_filename"]
        if e0 is None:
            e0 = find_e0(db, uid)
        comments = create_file_header(db, uid)
        # validate_path_exists(db, uid)

        # path_to_file = validate_file_exists(path_to_file, file_type="interp")
        path_to_file = hdr.start["interp_filename"]
        print(f">>>Path to file {path_to_file}")
        # try:
        if experiment == "fly_energy_scan":
            raw_df = load_dataset_from_files(db, uid)
            key_base = "i0"
        elif experiment == "fly_energy_scan_apb":
            apb_df, energy_df, energy_offset = load_apb_dataset_from_db(db, uid)
            raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)
            key_base = "i0"
        elif experiment == "fly_energy_scan_xs3":
            apb_df, energy_df, energy_offset = load_apb_dataset_from_db(db, uid)
            raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)

            apb_trig_timestamps = load_apb_trig_dataset_from_db(db, uid)
            xs3_dict = load_xs3_dataset_from_db(db, uid, apb_trig_timestamps)

            raw_df = {**raw_df, **xs3_dict}
            key_base = "CHAN1ROI1"
        elif experiment == "fly_energy_scan_xs3x":
            apb_df, energy_df, energy_offset = load_apb_dataset_from_db(db, uid)
            raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)

            apb_trig_timestamps = load_apb_trig_dataset_from_db(db, uid)
            xs3_dict = load_xs3x_dataset_from_db(db, uid, apb_trig_timestamps)

            raw_df = {**raw_df, **xs3_dict}
            key_base = "CHAN1ROI1"
        logger.info(f"Loading file successful for UID {uid}/{path_to_file}")
        # except:
        #     logger.info(f'Loading file failed for UID {uid}/{path_to_file}')
        try:
            interpolated_df = interpolate(raw_df, key_base=key_base)
            logger.info(f"Interpolation successful for {path_to_file}")
            # save_interpolated_df_as_file(path_to_file, interpolated_df, comments)
            new_md = {
                "xdi": generate_xdi_metadata(hdr),
                "interp_filename": path_to_file,
            }
            table = pyarrow.Table.from_pandas(interpolated_df, preserve_index=False)
            table_client = client.create_appendable_table(
                schema=table.schema,
                metadata=new_md,
                access_tags=["lightshow_project"],
            )
            table_client.append_partition(0, table)
            # client.write_table(
            #   interpolated_df,
            #   metadata=new_md,
            #   access_tags=[hdr.start["proposal"]],
            # )
        except:
            logger.info(f"Interpolation failed for {path_to_file}")
            # Enable this if you change filepath to a local one
            try:
                if e0 > 0:
                    print(
                        "Inside xas process try draw (e0 > 0) start time: ",
                        datetime.now(),
                    )
                    # binned_df = rebin(interpolated_df, e0)
                    binned_df = issrebin(interpolated_df, e0)

                    logger.info(f"Binning successful for {path_to_file}")
                    if experiment == "fly_energy_scan_apb":
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=True
                        )
                    elif experiment == "fly_energy_scan_xs3":
                        binned_df = average_roi_channels(binned_df)
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=True
                        )
                    elif experiment == "fly_energy_scan_xs3x":
                        binned_df = average_roi_channels_xs3x(binned_df)
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=True
                        )
                    else:
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=False
                        )
                    if draw_func_interp is not None:
                        draw_func_interp(interpolated_df)

                else:
                    print("Energy E0 is not defined")
            except Exception as e:
                logger.info(f"Binning failed for {path_to_file}")
                print(e)
            pass
    elif experiment.startswith("diffraction"):
        pass


def process_interpolate_bin(doc, db, draw_func_interp=None, draw_func_binnned=None):

    logger = get_logger()

    if "experiment" in db[doc["run_start"]].start.keys():
        uid = doc["run_start"]
        experiment = db[uid].start["experiment"]
        if experiment.startswith("fly"):
            path_to_file = db[uid].start["interp_filename"]
            e0 = find_e0(db, uid)
            comments = create_file_header(db, uid)
            validate_path_exists(db, uid)

            path_to_file = validate_file_exists(path_to_file, file_type="interp")
            print(f">>>Path to file {path_to_file}")
            # try:
            if experiment == "fly_energy_scan":
                raw_df = load_dataset_from_files(db, uid)
                key_base = "i0"
            elif experiment == "fly_energy_scan_apb":
                apb_df, energy_df, energy_offset = load_apb_dataset_from_db(db, uid)
                raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)
                key_base = "i0"
            elif experiment == "fly_energy_scan_xs3":
                apb_df, energy_df, energy_offset = load_apb_dataset_from_db(db, uid)
                raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)

                apb_trig_timestamps = load_apb_trig_dataset_from_db(db, uid)
                xs3_dict = load_xs3_dataset_from_db(db, uid, apb_trig_timestamps)
                raw_df = {**raw_df, **xs3_dict}
                key_base = "CHAN1ROI1"

            elif experiment == "fly_energy_scan_xs3x":
                apb_df, energy_df, energy_offset = load_apb_dataset_from_db(db, uid)
                raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)

                apb_trig_timestamps = load_apb_trig_dataset_from_db(db, uid)
                xs3_dict = load_xs3x_dataset_from_db(db, uid, apb_trig_timestamps)

                raw_df = {**raw_df, **xs3_dict}
                key_base = "CHAN1ROI1"
            logger.info(f"Loading file successful for UID {uid}/{path_to_file}")
            # except:
            #     logger.info(f'Loading file failed for UID {uid}/{path_to_file}')
            try:
                interpolated_df = interpolate(raw_df, key_base=key_base)
                logger.info(f"Interpolation successful for {path_to_file}")
                save_interpolated_df_as_file(path_to_file, interpolated_df, comments)
            except:
                logger.info(f"Interpolation failed for {path_to_file}")

            try:
                if e0 > 0:
                    print(
                        "Inside xas process try draw (e0 > 0) start time: ",
                        datetime.now(),
                    )
                    # binned_df = rebin(interpolated_df, e0)
                    binned_df = issrebin(interpolated_df, e0)

                    logger.info(f"Binning successful for {path_to_file}")
                    if experiment == "fly_energy_scan_apb":
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=True
                        )
                    elif experiment == "fly_energy_scan_xs3":
                        binned_df = average_roi_channels(binned_df)
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=True
                        )
                    elif experiment == "fly_energy_scan_xs3x":
                        binned_df = average_roi_channels_xs3x(binned_df)
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=True
                        )
                    else:
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=False
                        )
                    if draw_func_interp is not None:
                        draw_func_interp(interpolated_df)

                else:
                    print("Energy E0 is not defined")
            except Exception as e:
                logger.info(f"Binning failed for {path_to_file}")
                print(e)
                pass
        elif experiment.startswith("diffraction"):
            pass


def process_interpolate_only(doc, db):
    if "experiment" in db[doc["run_start"]].start.keys():
        if db[doc["run_start"]].start["experiment"] == "fly_energy_scan":
            raw_df = load_dataset_from_files(db, doc["run_start"])
            interpolated_df = interpolate(raw_df)
            return interpolated_df


def process_interpolate_bin_new(
    doc, db, draw_func_interp=None, draw_func_binnned=None, load_mca=False
):

    logger = get_logger()

    if "experiment" in db[doc["run_start"]].start.keys():
        uid = doc["run_start"]
        experiment = db[uid].start["experiment"]
        if experiment.startswith("fly"):
            path_to_file = db[uid].start["interp_filename"]
            e0 = find_e0(db, uid)
            comments = create_file_header(db, uid)
            validate_path_exists(db, uid)

            path_to_file = validate_file_exists(path_to_file, file_type="interp")
            print(f">>>Path to file {path_to_file}")
            # try:
            if experiment == "fly_energy_scan":
                raw_df = load_dataset_from_files(db, uid)
                key_base = "i0"
            elif experiment == "fly_energy_scan_apb":
                apb_df, energy_df, energy_offset = load_apb_dataset_from_db(db, uid)
                raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)
                key_base = "i0"
            elif experiment == "fly_energy_scan_xs3" and (load_mca is False):
                apb_df, energy_df, energy_offset = load_apb_dataset_from_db(db, uid)
                raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)

                apb_trig_timestamps = load_apb_trig_dataset_from_db(db, uid)
                xs3_dict = load_xs3_dataset_from_db(db, uid, apb_trig_timestamps)

                raw_df = {**raw_df, **xs3_dict}
                key_base = "CHAN1ROI1"
            elif experiment == "fly_energy_scan_xs3" and (load_mca is True):
                apb_df, energy_df, energy_offset = load_apb_dataset_from_db(db, uid)
                raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)
                apb_trig_timestamps = load_apb_trig_dataset_from_db(db, uid)
                xs3_dict = load_xs3_dataset_from_db_new(db, uid, apb_trig_timestamps)
                raw_df = {**raw_df, **xs3_dict}
                key_base = "CHAN1ROI1"

            logger.info(f"Loading file successful for UID {uid}/{path_to_file}")
            # except:
            #     logger.info(f'Loading file failed for UID {uid}/{path_to_file}')
            try:
                if load_mca:
                    interpolated_df = interpolate_with_interp(raw_df, key_base=key_base)
                else:
                    interpolated_df = interpolate(raw_df, key_base=key_base)
                logger.info(f"Interpolation successful for {path_to_file}")
                save_interpolated_df_as_file(path_to_file, interpolated_df, comments)
            except:
                logger.info(f"Interpolation failed for {path_to_file}")

            try:
                if e0 > 0:
                    print(
                        "Inside xas process try draw (e0 > 0) start time: ",
                        datetime.now(),
                    )
                    # binned_df = rebin(interpolated_df, e0)
                    binned_df = issrebin(interpolated_df, e0)

                    logger.info(f"Binning successful for {path_to_file}")
                    if experiment == "fly_energy_scan_apb":
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=True
                        )
                    elif experiment == "fly_energy_scan_xs3" and (load_mca is False):
                        binned_df = average_roi_channels(binned_df)
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=True
                        )
                    elif experiment == "fly_energy_scan_xs3" and (load_mca is True):
                        binned_df = average_roi_channels(binned_df)
                        save_binned_df_as_hdf5_file(
                            path_to_file, binned_df, comments, reorder=True
                        )
                    else:
                        save_binned_df_as_file(
                            path_to_file, binned_df, comments, reorder=False
                        )
                    if draw_func_interp is not None:
                        draw_func_interp(interpolated_df)

                else:
                    print("Energy E0 is not defined")
            except Exception as e:
                logger.info(f"Binning failed for {path_to_file}")
                print(e)
                pass
        elif experiment.startswith("diffraction"):
            pass


def load_flyscan_dataset(tiled_client):
    experiment = tiled_client.start["experiment"]

    if experiment == "fly_energy_scan":
        raw_df = load_dataset_from_files(db, uid)

    elif experiment == "fly_energy_scan_apb":
        apb_df, energy_df, energy_offset = load_apb_dataset_from_tiled(tiled_client)
        raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)

    elif experiment == "fly_energy_scan_xs3":
        raise NotImplementedError(
            "Need to update and test the `load_xs3_dataset_from_tiled` function."
        )

        apb_df, energy_df, energy_offset = load_apb_dataset_from_tiled(tiled_client)
        raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)

        apb_trig_timestamps = load_apb_trig_dataset_from_tiled(tiled_client)
        xs3_dict = load_xs3_dataset_from_tiled(tiled_client, apb_trig_timestamps)

        raw_df = {**raw_df, **xs3_dict}

    elif experiment == "fly_energy_scan_xs3x":
        apb_df, energy_df, energy_offset = load_apb_dataset_from_tiled(tiled_client)
        raw_df = translate_apb_dataset(apb_df, energy_df, energy_offset)

        apb_trig_timestamps = load_apb_trig_dataset_from_tiled(tiled_client)
        xs3_dict = load_xs3x_dataset_from_tiled(tiled_client, apb_trig_timestamps)
        raw_df = {**raw_df, **xs3_dict}

    return raw_df


def find_key_base(tiled_client):
    experiment = tiled_client.start["experiment"]
    if experiment in ["fly_energy_scan", "fly_energy_scan_apb"]:
        return "i0"
    elif experiment in ["fly_energy_scan_xs3", "fly_energy_scan_xs3x"]:
        return "CHAN1ROI1"
    else:
        raise ValueError(
            f"Experiment {experiment} not recognized. "
            "Cannot determine key_base for interpolation."
        )


def process_interpolate_bin_with_tiled(tiled_client, tiled_writing_client, draw_func_interp=None, e0=None):
    logger = get_logger()
    print("SLEEPING")
    sleep(10)
    tiled_client.refresh()
    experiment = tiled_client.start["experiment"]
    uid = tiled_client.start["uid"]

    if experiment.startswith("fly"):
        path_to_file = tiled_client.start["interp_filename"]
        print(f">>>Path to file {path_to_file}")

        if e0 is None:
            e0 = float(tiled_client.start.get("e0", -1))

        comments = create_file_header_tiled(tiled_client)

        raw_df = load_flyscan_dataset(tiled_client)
        key_base = find_key_base(tiled_client)

        logger.info(f"Loading file successful for UID {uid}/{path_to_file}")

        ### Run Interpolation
        # try:
        interpolated_df = interpolate(raw_df, key_base=key_base)

        logger.info(f"Interpolation successful for {path_to_file}")

        ### This needs to be moved outside ###
        new_md = {
            "xdi": generate_xdi_metadata(tiled_client),
            "interp_filename": path_to_file,
        }
        
        # Change to "write appendable"
        table = pyarrow.Table.from_pandas(interpolated_df, preserve_index=False)
        table_client = tiled_writing_client.create_appendable_table(
            schema=table.schema,
            metadata=new_md,
            access_tags=["lightshow_project"],
        )
        table_client.append_partition(0, table)
        # client.write_table(
        #     interpolated_df,
        #     metadata=new_md,
        #     access_tags=["qas_processed"],
        # )
        ###########

        # except:
        # logger.info(f"Interpolation failed for {path_to_file}")
        # # Enable this if you change filepath to a local one
        # try:

        ### Run Binning
        if e0 > 0:
            print("Inside xas process try draw (e0 > 0) start time: ", datetime.now())
            # binned_df = rebin(interpolated_df, e0)
            binned_df = issrebin(interpolated_df, e0)

            if os.getenv("TEST") == "1":
                path_to_file = str(Path(__file__).parent / Path(path_to_file).name)

            logger.info(f"Binning successful for {path_to_file}")
            if experiment == "fly_energy_scan_apb":
                # save_binned_df_as_file(path_to_file, binned_df, comments, reorder=True)
                print("Saved to TILED")
            elif experiment == "fly_energy_scan_xs3":
                binned_df = average_roi_channels(binned_df)
                save_binned_df_as_file(path_to_file, binned_df, comments, reorder=True)
            elif experiment == "fly_energy_scan_xs3x":
                binned_df = average_roi_channels_xs3x(binned_df)
                save_binned_df_as_file(path_to_file, binned_df, comments, reorder=True)
            else:
                save_binned_df_as_file(path_to_file, binned_df, comments, reorder=False)
            if draw_func_interp is not None:
               draw_func_interp(interpolated_df)

        else:
            print("Energy E0 is not defined")
            # except Exception as e:
            #     logger.info(f"Binning failed for {path_to_file}")
            #     print(e)
            # pass
    elif experiment.startswith("diffraction"):
        pass
