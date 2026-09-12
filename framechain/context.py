# Global ETL context variable which has data set by FileProcessor and read by various Context operations or wrappers
transform_context = {}

def set_context(context_data):
    """
    Update context dictionary with provided data
    :param dict context_data:
    :return:
    """
    transform_context.update(context_data)