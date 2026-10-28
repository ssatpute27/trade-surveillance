"""Consistent fictional identities for the interview dataset.

Historical evidence and audit storage stay untouched. Presentation aliases keep
older saved reports readable alongside newly investigated cases.
"""
FIRST_NAMES=('Alex','Jordan','Sam','Riley','Casey','Drew','Morgan','Avery','Taylor','Cameron','Robin','Jamie',
             'Quinn','Parker','Reese','Blair','Skyler','Rowan','Hayden','Dakota','Finley','Sage','Emery','Kendall')
LAST_NAMES=('Bennett','Patel','Walker','Chen','Morgan','Sullivan','Reed','Brooks','Mitchell','Hayes','Shah','Collins',
            'Foster','Lawson','Campbell','Anderson','Nguyen','Ellis','Turner','Richardson','Grant','Williams','Coleman','Rivera')
TRADER_NAMES=tuple(f'{first} {last}' for first,last in zip(FIRST_NAMES,LAST_NAMES))
BOOK_NAMES=('Event Opportunities','Merger Arbitrage','Special Situations','Catalyst Strategies',
            'Equity Relative Value','Index Arbitrage','US Equity Execution','Portfolio Transitions',
            'Program Trading','Risk Facilitation','ETF Liquidity','Equity Market Making',
            'Central Risk','Delta Hedging','Block Facilitation','Inventory Management')
CLIENT_NAMES=('Willowcrest Pension Trust','Cedarbrook Retirement Fund','Stonehaven Asset Management','Westhaven Endowment',
              'Maplewood Investment Partners','Brookfield Heights Foundation','Fairwater Capital Partners','Oakridge Municipal Pension',
              'Alderstone Investment Trust','Pinehurst University Endowment','Clearbrook Wealth Management','Silvermere Retirement Trust',
              'Ashford County Pension','Lakewood Investment Council','Willowbank Family Office','Redwood Grove Endowment',
              'Northvale Capital Management','Ridgewater Retirement System','Cresthaven Insurance Portfolio','Elmbridge Investment Partners',
              'Hawthorne Valley Foundation','Meadowcrest Asset Management','Birchwater Pension Trust','Westbrook Hills Endowment')
ACCOUNT_NAMES=tuple(f'{name} Book' for name in BOOK_NAMES)+CLIENT_NAMES
ALIASES={f'{first} Demo-{i+1:02}':TRADER_NAMES[i] for i,first in enumerate(FIRST_NAMES)}
ALIASES.update({f'Simulated {"Internal Book" if i<16 else "Institutional Client"} {i+1:02}':name for i,name in enumerate(ACCOUNT_NAMES)})


def display_identities(value):
    """Return a presentation copy; IDs, numbers, hashes and original storage are retained."""
    if isinstance(value,str):
        for old,new in ALIASES.items():value=value.replace(old,new)
        return value
    if isinstance(value,list):return [display_identities(item) for item in value]
    if isinstance(value,dict):return {key:display_identities(item) for key,item in value.items()}
    return value
