from algopy import (
    ARC4Contract,
    Asset,
    BoxMap,
    Global,
    Txn,
    UInt64,
    arc4,
    gtxn,
    itxn,
    subroutine,
)


class ListingKey(arc4.Struct):
    owner: arc4.Address
    asset: arc4.UInt64


class ListingValue(arc4.Struct):
    deposited: arc4.UInt64
    unitary_price: arc4.UInt64


class DigitalMarketplace(ARC4Contract):
    def __init__(self) -> None:
        self.listings = BoxMap(ListingKey, ListingValue)

    @subroutine
    def get_box_mbr(self) -> UInt64:
        # Box: Key -> Value  // [address,asset_id] -> [quantity, price]
        # Boxes MBR -> 0.0025 por Box + 0.0004 por cada byte
        # MBR del caso de uso -> [32 Bytes, 8 Bytes] -> [8 Bytes, 8 Bytes] = 56 Bytes
        # MBR del caso = prefix + 0.0025 + 0.0004*56
        return (
            2_500
            + (
                # Key length
                self.listings.key_prefix.length
                + 32
                + 8
                # Value length
                + 8
                + 8
            )
            * 400
        )

    # Recibir o permitir assets de venta
    @arc4.abimethod
    def allow_asset(self, mbr_pay: gtxn.PaymentTransaction, asset: Asset) -> None:
        # Verificar que el contrato no haya hecho optin antes al asset
        assert not Global.current_application_address.is_opted_in(asset)

        # Verificar la transacción del MBR
        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == Global.asset_opt_in_min_balance

        # Hacer el optin del contrato al asset
        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Global.current_application_address,
            asset_amount=0,
            fee=0,
        ).submit()

    # Depositar assets en el contrato
    @arc4.abimethod
    def first_deposit(
        self,
        mbr_pay: gtxn.PaymentTransaction,
        xfer: gtxn.AssetTransferTransaction,
        unitary_price: arc4.UInt64,
    ) -> None:

        assert mbr_pay.sender == Txn.sender
        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == self.get_box_mbr()

        box_key = ListingKey(
            owner=arc4.Address(Txn.sender),
            asset=arc4.UInt64(xfer.xfer_asset.id),
        )

        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.sender == Txn.sender
        assert xfer.asset_amount > 0

        self.listings[box_key] = ListingValue(
            deposited=arc4.UInt64(xfer.asset_amount),
            unitary_price=unitary_price,
        )

    @arc4.abimethod
    def deposit(
        self,
        xfer: gtxn.AssetTransferTransaction,
    ) -> None:
        box_key = ListingKey(
            owner=arc4.Address(Txn.sender),
            asset=arc4.UInt64(xfer.xfer_asset.id),
        )

        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.sender == Txn.sender
        assert xfer.asset_amount > 0

        self.listings[box_key].deposited = arc4.UInt64(
            self.listings[box_key].deposited.native + xfer.asset_amount
        )

    # Funcion de modificar o definir el precio de venta
    @arc4.abimethod
    def set_price(
        self,
        unitary_price: arc4.UInt64,
        asset: Asset,
    ) -> None:
        box_key = ListingKey(
            owner=arc4.Address(Txn.sender),
            asset=arc4.UInt64(asset.id),
        )

        self.listings[box_key].unitary_price = unitary_price

    # Funcion de compra de assets
    @arc4.abimethod
    def buy(
        self,
        asset: Asset,
        buy_pay: gtxn.PaymentTransaction,
        quantity: UInt64,
        owner: arc4.Address,
    ) -> None:
        box_key = ListingKey(
            owner=owner,
            asset=arc4.UInt64(asset.id),
        )

        listing = self.listings[box_key].copy()

        assert buy_pay.receiver.bytes == owner.bytes
        assert buy_pay.sender == Txn.sender
        assert buy_pay.amount == listing.unitary_price.native * quantity

        self.listings[box_key].deposited = arc4.UInt64(
            listing.deposited.native - quantity
        )

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Txn.sender,
            asset_amount=quantity,
        ).submit()

    # Retirar sus ganancias y assets restantes
    @arc4.abimethod
    def withdraw(
        self,
        asset: Asset,
    ) -> None:
        box_key = ListingKey(
            owner=arc4.Address(Txn.sender),
            asset=arc4.UInt64(asset.id),
        )

        listing = self.listings[box_key].copy()

        current_deposited = listing.deposited.native
        del self.listings[box_key]

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_amount=current_deposited,
            asset_receiver=Txn.sender,
            fee=0,
        ).submit()

        itxn.Payment(
            receiver=Txn.sender,
            amount=self.get_box_mbr(),
            fee=0,
        ).submit()

    @arc4.abimethod(readonly=True)
    def get_listings_mbr(self) -> UInt64:
        return self.get_box_mbr()
