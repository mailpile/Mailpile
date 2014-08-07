var SetupMagic = {
  providers: {
     'gmail.com': 'gmail' ,
     'googlemail.com': 'gmail',
     'hotmail.com': 'outlook',
     'outlook.com': 'outlook',
     'yahoo.com': 'yahoo'
  },
  presets: {
    gmail: {
      sources: {
        name: 'Gmail Source',
        host: 'imap.gmail.com',
        port: 993,
        protocol: 'imap_ssl'
      },
      sending: {
        name: 'Gmail Sending',
        host: 'smtp.gmail.com',
        port: 587,
        protocol: 'smtp'
      }
    },
    outlook: {
      sources: {
        name: 'Outlook Source',
        host: 'imap-mail.outlook.com',
        port: 993,
        protocol: 'imap_ssl'
      },
      sending: {
        name: 'Outlook Sending',
        host: 'smtp-mail.outlook.com',
        port: 587,
        protocol: 'smtp'
      }
    },
    yahoo: {
      sources: {
        name: 'Yahoo Source',
        host: 'imap.mail.yahoo.com',
        port: 993,
        protocol: 'imap_ssl'
      },
      sending: {
        name: 'Yahoo Sending',
        host: 'smtp.mail.yahoo.com',
        port: 587,
        protocol: 'smtp'
      }
    }
  }
};