from typing import List

class Order:
    def __init__(self, PONumber: str):
        self.PONumber = PONumber

class Invoice:
    def __init__(self, VendorName: str, VendorVATRegistrationNumber: str, InvoiceOrCredit: str, InvoiceNumber: str, CreditReference: str, InvoiceDate: str, Currency: str, NetAmount: str, TaxAmount: str, Freight: str, MiscCharges: str, TotalAmount: str, Orders: List[Order]):
        self.VendorName = VendorName
        self.VendorVATRegistrationNumber = VendorVATRegistrationNumber
        self.InvoiceOrCredit = InvoiceOrCredit
        self.InvoiceNumber = InvoiceNumber
        self.CreditReference = CreditReference
        self.InvoiceDate = InvoiceDate
        self.Currency = Currency
        self.NetAmount = NetAmount
        self.TaxAmount = TaxAmount
        self.Freight = Freight
        self.MiscCharges = MiscCharges
        self.TotalAmount = TotalAmount
        self.Orders = [Order(**order) for order in Orders]
