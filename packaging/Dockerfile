FROM centos:7
RUN yum install -y gcc
RUN yum install -y python-devel

RUN curl -O https://bootstrap.pypa.io/get-pip.py
RUN python get-pip.py

RUN pip install wagon

RUN mkdir /plugin
RUN mkdir /artifacts

CMD wagon create -f /plugin -o /artifacts

