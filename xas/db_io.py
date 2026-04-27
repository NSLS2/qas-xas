import pandas as pd
import numpy as np
from . import xray
from itertools import product
from copy import deepcopy
import time as ttime


def load_apb_dataset_from_db(db, uid):
    print(f'READING DATABROKER - {ttime.time()}')
    hdr = db[uid]
    if hdr.start['hutch'] == 'b':
        apb_dataset = deepcopy(list(hdr.data(stream_name='apb_stream', field='apb_stream'))[0])
    if hdr.start['hutch'] == 'c':
        apb_dataset = deepcopy(list(hdr.data(stream_name='apb_stream_c', field='apb_stream_c'))[0])

    # apb_dataset = list(hdr.data(stream_name='apb_stream', field='apb_stream'))[0]
    energy_dataset =  list(hdr.data(stream_name='pb1_enc1',field='pb1_enc1'))[0]
    if not isinstance(energy_dataset, pd.DataFrame):
        energy_dataset = pd.DataFrame(energy_dataset)
    else:
        pass
    angle_offset = -float(hdr['start']['angle_offset'])
    # ch_offset_keys = [key for key in hdr.start.keys() if key.startswith('ch') and key.endswith('_offset')]
    # ch_offsets = np.array([hdr.start[key] for key in ch_offset_keys])

    ch_offsets = get_ch_properties(hdr.start, 'ch', '_offset')*1e3 #offsets are ib mV but the readings are in uV
    ch_gains = get_ch_properties(hdr.start, 'ch', '_amp_gain')

    if not isinstance(apb_dataset, pd.DataFrame):
        apb_dataset = pd.DataFrame(apb_dataset)
    else:
        pass
    
    # Tiled returns data in a different dtype
    apb_dtype = apb_dataset.astype('float64')
    apb_dtype.iloc[:, 1:] -= ch_offsets
    apb_dtype.iloc[:, 1:] /= 1e6
 #   apb_dataset.iloc[:, 1:] /= (10**ch_gains)

    return apb_dtype, energy_dataset, angle_offset


def load_apb_dataset_from_tiled(tiled_client):
    print(f'LOADING APB DATA FROM TILED - {ttime.time()}')

    apb_stream_name = 'apb_stream' if tiled_client.start['hutch'] == 'b' else 'apb_stream_c'
    apb_dataset = pd.DataFrame(tiled_client[f'{apb_stream_name}/{apb_stream_name}'].read().ravel())

    energy_dataset = pd.DataFrame(tiled_client['pb1_enc1/pb1_enc1'].read().ravel())
    angle_offset = -float(tiled_client.start['angle_offset'])

    ch_offsets = get_ch_properties(tiled_client.start, 'ch', '_offset')*1e3  # offsets are ib mV but the readings are in uV
    ch_gains = get_ch_properties(tiled_client.start, 'ch', '_amp_gain')
    
    # Tiled returns data in a different dtype
    apb_dtype = apb_dataset.astype('float64')
    apb_dtype.iloc[:, 1:] -= ch_offsets
    apb_dtype.iloc[:, 1:] /= 1e6
 #   apb_dataset.iloc[:, 1:] /= (10**ch_gains)

    return apb_dtype, energy_dataset, angle_offset


def load_apb_trig_dataset_from_tiled(tiled_client, use_fall=True, stream_name='apb_trigger'):

    data = tiled_client[f'{stream_name}/{stream_name}'].read().ravel()
    timestamps = data['timestamp']
    transitions = data['transition']  # 0 or 1

    n_all = np.bincount(transitions, minlength=2).min()  # min number of rises and falls to ensure pairs
    if use_fall:
        apb_trig_timestamps = (timestamps[transitions == 1][:n_all] + timestamps[transitions == 0][:n_all])/2
    else:
        rises = timestamps[transitions == 1]
        apb_trig_timestamps = rises[:n_all] + np.mean(np.diff(rises))/2

    return apb_trig_timestamps


def load_xs3_dataset_from_tiled(tiled_client, apb_trig_timestamps):
    # NOTE: not tested

    arr = tiled_client['xs_stream/xs_stream']
    n_spectra = arr.size
    xs_timestamps = apb_trig_timestamps[:n_spectra]
    chan_roi_names = [f'CHAN{c}ROI{r}' for c, r in product([1, 2, 3, 4, 6], [1, 2, 3, 4])]
    spectra = {}

    breakpoint()

    for j, chan_roi in enumerate(chan_roi_names):
        this_spectrum = np.zeros(n_spectra)

        for i in range(n_spectra):
            this_spectrum[i] = arr[i+1, chan_roi]

        spectra[chan_roi] = pd.DataFrame(np.vstack((xs_timestamps, this_spectrum)).T, columns=['timestamp', chan_roi])

    return spectra


def load_xs3x_dataset_from_tiled(tiled_client, apb_trig_timestamps):
    print("LOADING XS3X DATA FROM TILED - ", ttime.time())

    arr = tiled_client['xsx_stream/xsx_stream']
    roi_stream = tiled_client['baseline'].read()
    n_spectra = arr.shape[0]

    # NOTE: tempoarily limit the number of spectra for testing
    # !!!!!!!! REMOVE THIS IN PRODUCTION !!!!!!!
    # See below for another line to uncomment in production
    n_spectra = min(7, n_spectra)

    xs_timestamps = apb_trig_timestamps[:n_spectra]

    chan_roi_limits_mins = [f'xsx_stream_channel{c:02d}_mcaroi{r:02d}_min_x' for c, r in product([1, 3, 4, 5, 6, 7, 8], [1, 2, 3, 4])]
    chan_roi_limits_sizes = [f'xsx_stream_channel{c:02d}_mcaroi{r:02d}_size_x' for c, r in product([1, 3, 4, 5, 6, 7, 8], [1, 2, 3, 4])]
    chan_roi_names = [f'CHAN{c}ROI{r}' for c, r in product([1, 3, 4, 5, 6, 7, 8], [1, 2, 3, 4])]
    spectra = {}

    for chn in [1, 3, 4, 5, 6, 7, 8]:
        for roin in [1, 2, 3 ,4]:
            r_min = roi_stream[f'xsx_stream_channel{chn:02d}_mcaroi{roin:02d}_min_x'].values[1]
            r_size = roi_stream[f'xsx_stream_channel{chn:02d}_mcaroi{roin:02d}_size_x'].values[1] or 1

            r_spectrum = np.sum(arr[:n_spectra, chn-1, r_min:r_min+r_size], axis=1)    # REMOVE THIS LINE IN PRODUCTION; uncomment below
            # r_spectrum = np.sum(arr[:, chn-1, r_min:r_min+r_size], axis=1)
            roi_name = f'CHAN{chn}ROI{roin}'
            spectra[roi_name] = pd.DataFrame(np.vstack((xs_timestamps, r_spectrum)).T, columns=['timestamp', roi_name])

        print(f'Finished processing channel {chn} at time {ttime.time()}')

    # for chn in [1, 3, 4, 5, 6, 7, 8]:
    #     spectra[f'channel_{chn}'] = pd.DataFrame({'timestamp': xs_timestamps,
    #                                               f'channel_{chn}' : [row.tolist() for row in arr[:, chn-1, :]]})
                                                 #  [arr[:, chn-1, :]]),
                                                 # columns=['timestamp', f'channel_{chn}'])

    # for j, chan_roi in enumerate(chan_roi_names):
    #     this_spectrum = np.zeros(n_spectra)
    #
    #     for i in range(n_spectra):
    #         this_spectrum[i] = t[i+1][chan_roi]
    #
    #     spectra[chan_roi] = pd.DataFrame(np.vstack((xs_timestamps, this_spectrum)).T, columns=['timestamp', chan_roi])

    return spectra


def get_ch_properties(hdr_start, start, end):
    ch_keys = [key for key in hdr_start.keys() if key.startswith(start) and key.endswith(end)]
    return np.array([hdr_start[key] for key in ch_keys])



def translate_apb_dataset(apb_dataset, energy_dataset, angle_offset,):

    data_dict= {}

    # Add each channel as a separate DataFrame to the data_dict
    for column in set(apb_dataset.columns).difference({'timestamp'}):
        data_dict[column]=pd.DataFrame({"timestamp": apb_dataset['timestamp'],
                                              "adc": apb_dataset[column]})

    # Translate encoder values to energy and add to the data_dict
    enc = energy_dataset['encoder'].apply(lambda x: int(x) if int(x) <= 0 else -(int(x) ^ 0xffffff - 1))
    data_dict['energy'] = pd.DataFrame({"timestamp": energy_dataset['ts_s'] + energy_dataset['ts_ns']/1E09,
                             "encoder": xray.encoder2energy(enc, 26222.222222222223, angle_offset)})

    return data_dict


def load_apb_trig_dataset_from_db(db, uid, use_fall=True, stream_name='apb_trigger'):

    hdr = db[uid]
    t = hdr.table(stream_name=stream_name, fill=True)
    timestamps = t[stream_name][1]['timestamp'].values
    transitions = t[stream_name][1]['transition'].values
    n_0 = np.sum(transitions == 0)
    n_1 = np.sum(transitions == 1)
    n_all = np.min([n_0, n_1])
    if use_fall:
        apb_trig_timestamps = (timestamps[transitions == 1][:n_all] + timestamps[transitions == 0][:n_all])/2
    else:
        rises = timestamps[transitions == 1]
        apb_trig_timestamps = rises[:n_all] + np.mean(np.diff(rises))/2
    return apb_trig_timestamps


def load_xs3_dataset_from_db(db, uid, apb_trig_timestamps):
    hdr = db[uid]
    t = hdr.table(stream_name='xs_stream', fill=True)['xs_stream']
    n_spectra = t.size
    xs_timestamps = apb_trig_timestamps[:n_spectra]
    chan_roi_names = [f'CHAN{c}ROI{r}' for c, r in product([1, 2, 3, 4, 6], [1, 2, 3, 4])]
    spectra = {}

    for j, chan_roi in enumerate(chan_roi_names):
        this_spectrum = np.zeros(n_spectra)

        for i in range(n_spectra):
            this_spectrum[i] = t[i+1][chan_roi]

        spectra[chan_roi] = pd.DataFrame(np.vstack((xs_timestamps, this_spectrum)).T, columns=['timestamp', chan_roi])

    return spectra


def load_xs3x_dataset_from_db(db, uid, apb_trig_timestamps):
    print("NOW load_xs3x_dataset_from_db")
    hdr = db[uid]
    t = np.stack(hdr.table(stream_name='xsx_stream', fill=True)['xsx_stream'].to_numpy())
    roi_stream = hdr.table(stream_name='baseline')

    #['xsx_stream_channel02_mcaroi01_size_x'][1]
    n_spectra = t.shape[0]
    xs_timestamps = apb_trig_timestamps[:n_spectra]

    chan_roi_limits_mins = [f'xsx_stream_channel{c:02d}_mcaroi{r:02d}_min_x' for c, r in product([1, 3, 4, 5, 6, 7, 8], [1, 2, 3, 4])]
    chan_roi_limits_sizes = [f'xsx_stream_channel{c:02d}_mcaroi{r:02d}_size_x' for c, r in product([1, 3, 4, 5, 6, 7, 8], [1, 2, 3, 4])]
    chan_roi_names = [f'CHAN{c}ROI{r}' for c, r in product([1, 3, 4, 5, 6, 7, 8], [1, 2, 3, 4])]
    spectra = {}

    for chn in [1, 3, 4, 5, 6, 7, 8]:
        for roin in [1, 2, 3 ,4]:
            r_min = roi_stream[f'xsx_stream_channel{chn:02d}_mcaroi{roin:02d}_min_x'][1]
            r_size = roi_stream[f'xsx_stream_channel{chn:02d}_mcaroi{roin:02d}_size_x'][1]
            if r_size == 0:
                r_size = 1
            # t_slice = t[:, chn-1, r_min:r_min+r_size]
            # print(t_slice.shape)
            r_spectrum = np.sum(t[:, chn-1, r_min:r_min+r_size], axis=1)
            roi_name = f'CHAN{chn}ROI{roin}'
            spectra[roi_name] = pd.DataFrame(np.vstack((xs_timestamps, r_spectrum)).T, columns=['timestamp', roi_name])

    # for chn in [1, 3, 4, 5, 6, 7, 8]:
    #     spectra[f'channel_{chn}'] = pd.DataFrame({'timestamp': xs_timestamps,
    #                                               f'channel_{chn}' : [row.tolist() for row in t[:, chn-1, :]]})
                                                 #  [t[:, chn-1, :]]),
                                                 # columns=['timestamp', f'channel_{chn}'])

    # for j, chan_roi in enumerate(chan_roi_names):
    #     this_spectrum = np.zeros(n_spectra)
    #
    #     for i in range(n_spectra):
    #         this_spectrum[i] = t[i+1][chan_roi]
    #
    #     spectra[chan_roi] = pd.DataFrame(np.vstack((xs_timestamps, this_spectrum)).T, columns=['timestamp', chan_roi])

    return spectra


def load_xs3_dataset_from_db_new(db, uid, apb_trig_timestamps):
    hdr = db[uid]
    t = hdr.table(stream_name='xs_stream', fill=True)['xs_stream']
    n_spectra = t.size
    xs_timestamps = apb_trig_timestamps[:n_spectra]
    chan_roi_names = [f'CHAN{c}ROI{r}' for c, r in product([1, 2, 3, 4, 6], [1, 2, 3, 4])]
    spectra = {}

    for j, chan_roi in enumerate(chan_roi_names):
        this_spectrum = np.zeros(n_spectra)

        for i in range(n_spectra):
            this_spectrum[i] = t[i+1][chan_roi]

        spectra[chan_roi] = pd.DataFrame(np.vstack((xs_timestamps, this_spectrum)).T, columns=['timestamp', chan_roi])

    _buffer = {}
    for key in ['ch_1', 'ch_2', 'ch_3', 'ch_4']:
        _buffer[key] = [i[key].astype(np.float64) for i in list(hdr.data(stream_name='xs_stream', field='xs_stream'))]
        _buffer_df = pd.DataFrame(_buffer)
        spectra[key] = pd.DataFrame(np.vstack((xs_timestamps.astype('float'), _buffer_df[key])).T, columns=['timestamp', key])

    return spectra


def load_pil100k_dataset_from_db(db, uid, apb_trig_timestamps, input_type='hdf5'):
    hdr = db[uid]
    t = hdr.table(stream_name='pil100k_stream', fill=True)['pil100k_stream']
    spectra = {}
    n_images = t.shape[0]
    pil100k_timestamps = apb_trig_timestamps[:n_images]
    if input_type == 'tiff':
        image_array = np.array([i for i in t])
        rois = hdr.start['roi']


        for j in range(4):
            x, y, dx, dy = rois[j]
            this_spectrum = np.sum(image_array[:, y: (y + dy), x: (x + dx)], axis=(1,2)) # NOTE : flipped X and Y

            spectra[f'pil100k_ROI{j+1}'] = pd.DataFrame(np.vstack((pil100k_timestamps, this_spectrum)).T, columns=['timestamp', f'pil100k_ROI{j+1}'])
    elif input_type == 'hdf5':
        keys = t[1].keys()
        _spectra = np.zeros((n_images, len(keys)))
        for i in range(1, n_images + 1):
            for j, key in enumerate(keys):
                _spectra[i, j] = t[i][key]
        for j, key in enumerate(keys):
            spectra[key] =  pd.DataFrame(np.vstack((pil100k_timestamps, _spectra[:, j])).T, columns=['timestamp', f'pil100k_ROI{j+1}'])

    return spectra



def load_general_scan_dataset_from_db(db, uid):
    hdr = db[uid]



def plot_normalized(x, y, factor=1):
    x = np.array(x)
    y = np.array(y)

    y_norm = (y - y.min())/factor
    plt.plot(x, y_norm)


def plot_normalized_scan(db, uid, factor=1):
    hdr = db[uid]
    x = list(hdr.data('hhm_energy'))
    y = list(hdr.data('pil100k_stats1_total'))
    plot_normalized(x, y, factor)
