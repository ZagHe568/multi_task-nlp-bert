import torch
from torch import nn
from transformers import BertModel
from utils import to_device


class MultiTaskBert(nn.Module):
    def __init__(self, config):
        super(MultiTaskBert, self).__init__()
        self.config = config

        # BERT Model. We use a pre-trained one.
        self.bert = BertModel.from_pretrained('bert-base-uncased')

        self.fc_sst2 = nn.Linear(in_features=768, out_features=2)
        self.fc_stsb = nn.Linear(in_features=768, out_features=1)
        self.fc_qnli = nn.Linear(in_features=768, out_features=2)
        self.fc_snli = nn.Linear(in_features=768, out_features=3)

        if not config.multi_task:
            for param in self.fc_sst2.parameters():
                param.requires_grad = False
            for param in self.fc_stsb.parameters():
                param.requires_grad = False
            for param in self.fc_qnli.parameters():
                param.requires_grad = False

        self.dropout_emb = nn.Dropout(p=config.dropout_emb)

        # Bert parameters not included because we haven't deifined BERT yet
        self.print_req_grad_params()

    def forward(self, snli_token_ids, snli_seg_ids, snli_mask_ids,
                sst2_token_ids=None, sst2_mask_ids=None,
                stsb_token_ids=None, stsb_seg_ids=None, stsb_mask_ids=None,
                qnli_token_ids=None, qnli_seg_ids=None, qnli_mask_ids=None,):

        # SNLI
        snli_token_ids = snli_token_ids.to(self.fc_sst2.weight.device)
        # batch_size*max_len --> batch_size*max_len*emb_dim
        snli_emb = self.bert(snli_token_ids, token_type_ids=snli_seg_ids, attention_mask=snli_mask_ids)[0]
        # batch_size*max_len*emb_dim --> batch_size*emb_dim
        # we only need the representation of the first token to represent the entire sequence/pair
        snli_emb = snli_emb[:, 0]
        snli_emb = self.dropout_emb(snli_emb)
        snli_output = self.fc_snli(snli_emb)
        del snli_token_ids  # release cuda memory
        torch.cuda.empty_cache()

        if self.training and self.config.multi_task:
            # SST-2
            sst2_token_ids = sst2_token_ids.to(self.fc_sst2.weight.device)
            sst2_token_ids, sst2_mask_ids = to_device(sst2_token_ids, sst2_mask_ids, device=self.fc_sst2.weight.device)
            sst2_emb = self.bert(sst2_token_ids, attention_mask=sst2_mask_ids)[0]
            sst2_emb = sst2_emb[:, 0]
            sst2_emb = self.dropout_emb(sst2_emb)
            sst2_output = self.fc_sst2(sst2_emb)
            del sst2_token_ids  # release cuda memory
            torch.cuda.empty_cache()

            # STS-B
            stsb_token_ids = stsb_token_ids.to(self.fc_sst2.weight.device)
            stsb_emb = self.bert(stsb_token_ids, token_type_ids=stsb_seg_ids, attention_mask=stsb_mask_ids)[0]
            stsb_emb = stsb_emb[:, 0]
            stsb_emb = self.dropout_emb(stsb_emb)
            stsb_output = self.fc_stsb(stsb_emb)
            del stsb_token_ids  # release cuda memory
            torch.cuda.empty_cache()

            # QNLI
            qnli_token_ids = qnli_token_ids.to(self.fc_sst2.weight.device)
            qnli_emb = self.bert(qnli_token_ids)[0]
            qnli_emb = qnli_emb[:, 0]
            qnli_emb = self.dropout_emb(qnli_emb)
            qnli_output = self.fc_qnli(qnli_emb)
            del qnli_token_ids  # release cuda memory
            torch.cuda.empty_cache()

            return snli_output, sst2_output, stsb_output, qnli_output

        else:
            return snli_output, None, None, None

    def print_req_grad_params(self):
        total_size = 0

        def multiply_iter(p_list):
            out = 1
            for _p in p_list:
                out *= _p
            return out

        for name, p in self.named_parameters():
            if p.requires_grad:
                n_params = multiply_iter(p.size())  # the product of all dimensions, i.e., # of parameters
                total_size += n_params

        print('#Model parameters: {:,}'.format(total_size))
