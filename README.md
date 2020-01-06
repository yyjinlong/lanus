Lanus
----

## Features

* OTP Certification

* LDAP User Manage

* Command Record

* Log clean


## Install

    $ python3 tools/install_venv.py
    $ tools/with_venv.sh pip install git+git://github.com/yyjinlong/paramiko.git#egg=paramiko
    $ tools/with_venv.sh python setup.py develop


## Usage

    bastion server:
    $ tools/with_venv.sh lanus-bastion --config-file=etc/dev.conf


## Mock Test

    mock api server:
    $ tools/with_venv.sh lanus-mockapi --config-file=etc/dev.conf
