from etl_framework.operations.pandas.base import ColumnOperation


class ECGIFromLocationInformation(ColumnOperation):
    """
    Vectorised transformation to extract ECGI from UserLocationInformation string of type '18',
    which contains TAI and eCGI. Input string content is:
    0-2: Location Type (x18)
    2-12: TAI (MCC + MNC + TAC)
    12-: eCGI (MCC + MNC + ECI)
    """

    def __call__(self, uli_series):
        mcc = uli_series[13:11:-1] + uli_series[15]  # 505
        mnc = uli_series[17:15:-1]  # 01
        eci = uli_series[18:]
        return mcc + mnc + eci


def nibble_swap_plmn_identifier(plmn_id_str):
    """
    PLMNID is represented by nibble-swapped bytes in raw data, need to swap digits
    Go from 05F510 to 50501
    :param plmn_id_str:
    :return:
    """
    return plmn_id_str[1::-1] + plmn_id_str[3] + plmn_id_str[5:3:-1]