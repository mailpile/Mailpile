# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure("2") do |config|

  config.vm.box     = 'debian7'
  config.vm.box_url = 'http://puppet-vagrant-boxes.puppetlabs.com/debian-70rc1-x64-vbox4210.box'

  config.vm.provider "virtualbox" do |v|
    v.customize ["modifyvm", :id, "--memory", 1024]
  end

  config.vm.synced_folder '.', '/srv/Mailpile'
  config.vm.network :forwarded_port, guest: 33411, host: 33411
  config.vm.provision :shell, :path => 'scripts/vagrant_bootstrap.sh'
end
