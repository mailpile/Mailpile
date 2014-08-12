var SetupMagic = {
  can_dance: false,
  random_id: Math.random().toString(36).substring(2),
  providers: {
     'gmail.com': 'gmail' ,
     'googlemail.com': 'gmail',
     'hotmail.com': 'outlook',
     'outlook.com': 'outlook',
     'yahoo.com': 'yahoo'
  },
  presets: {
    gmail: {
      source: {
        name: 'Gmail Source',
        host: 'imap.gmail.com',
        port: 993,
        protocol: 'imap_ssl',
        interval: 300,
        'discovery.paths': []
      },
      sending: {
        name: 'Gmail Sending',
        host: 'smtp.gmail.com',
        port: 587,
        protocol: 'smtp'
      }
    },
    outlook: {
      source: {
        name: 'Outlook Source',
        host: 'imap-mail.outlook.com',
        port: 993,
        protocol: 'imap_ssl',
        interval: 300,
        'discovery.paths': []
      },
      sending: {
        name: 'Outlook Sending',
        host: 'smtp-mail.outlook.com',
        port: 587,
        protocol: 'smtp'
      }
    },
    yahoo: {
      source: {
        name: 'Yahoo Source',
        host: 'imap.mail.yahoo.com',
        port: 993,
        protocol: 'imap_ssl',
        interval: 300,
        'discovery.paths': []
      },
      sending: {
        name: 'Yahoo Sending',
        host: 'smtp.mail.yahoo.com',
        port: 587,
        protocol: 'smtp'
      }
    }
  },
  processAdd: function(auth_data) {

    console.log('inside of processAdd');
    console.log(auth_data);

    var provider = this.can_dance;
    var provider_data = this.presets[provider];

    console.log(provider_data);

    // Add Sending
    var sending_data = _.extend(provider_data.sending, auth_data);
    sending_data['_section'] = 'routes.' + this.random_id;

    Mailpile.API.settings_set_post(sending_data, function(result) {
      console.log('adding sending');
      console.log(result);
    });

    // Add Source
    var source_data = _.extend(provider_data.source, auth_data);
    source_data['_section'] = 'sources.' + this.random_id;

    Mailpile.API.settings_set_post(source_data, function(result) {
      console.log('adding source');
      console.log(result);
    });
  }
};