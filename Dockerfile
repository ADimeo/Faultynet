FROM ubuntu:22.04
LABEL maintainer="antonio.dimeo@student.hpi.de"
ENV TZ=Europe/PARIS \
    DEBIAN_FRONTEND=noninteractive

# install required packages
RUN apt-get clean
RUN apt-get update \
    && apt-get install -y  git \
    net-tools \
    aptitude \
    build-essential \
    python3-setuptools \
    python3-dev \
    python3-pip \
    software-properties-common \
    ansible \
    curl \
    iptables \
    iputils-ping \
    sudo

# install containernet (using its Ansible playbook)
COPY . /Faultynet
WORKDIR /Faultynet/ansible
RUN ansible-playbook -i "localhost," -c local --skip-tags "notindocker" install.yml
WORKDIR /Faultynet
RUN make develop

# Hotfix: https://github.com/pytest-dev/pytest/issues/4770
RUN pip3 install "more-itertools<=5.0.0"

# tell containernet that it runs in a container
ENV CONTAINERNET_NESTED 1

# Important: This entrypoint is required to start the OVS service
ENTRYPOINT ["util/docker/entrypoint.sh"]
CMD ["python3", "examples/containernet_example.py"]

