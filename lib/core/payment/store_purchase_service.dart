import 'dart:async';

import 'package:in_app_purchase/in_app_purchase.dart';

import '../api/app_models.dart';
import '../config/app_capabilities.dart';

class StorePurchaseReceipt {
  const StorePurchaseReceipt({
    required this.provider,
    required this.packageId,
    required this.productId,
    required this.transactionId,
    required this.purchaseToken,
    required this.verificationData,
    required this.verificationSource,
  });

  final String provider;
  final String packageId;
  final String productId;
  final String transactionId;
  final String purchaseToken;
  final String verificationData;
  final String verificationSource;
}

abstract class StorePurchaseLauncher {
  Future<StorePurchaseReceipt> purchase({
    required String provider,
    required PaymentPackage package,
  });
}

class NativeStorePurchaseLauncher implements StorePurchaseLauncher {
  NativeStorePurchaseLauncher({
    InAppPurchase? inAppPurchase,
    this.timeout = const Duration(minutes: 2),
  }) : _inAppPurchase = inAppPurchase ?? InAppPurchase.instance;

  final InAppPurchase _inAppPurchase;
  final Duration timeout;

  @override
  Future<StorePurchaseReceipt> purchase({
    required String provider,
    required PaymentPackage package,
  }) async {
    if (!_isStoreProvider(provider)) {
      throw ArgumentError.value(provider, 'provider', 'Not a store provider.');
    }
    if (!await _inAppPurchase.isAvailable()) {
      throw StateError('Store purchases are unavailable on this device.');
    }

    final productId = package.storeProductId;
    final productResponse =
        await _inAppPurchase.queryProductDetails({productId});
    final productError = productResponse.error;
    if (productError != null) {
      throw StateError(productError.message);
    }
    if (productResponse.productDetails.isEmpty) {
      throw StateError('Store product $productId is not configured.');
    }
    final productDetails = productResponse.productDetails.firstWhere(
      (product) => product.id == productId,
      orElse: () => productResponse.productDetails.first,
    );

    final completer = Completer<StorePurchaseReceipt>();
    late final StreamSubscription<List<PurchaseDetails>> subscription;
    subscription = _inAppPurchase.purchaseStream.listen(
      (purchases) async {
        for (final purchase in purchases) {
          if (purchase.productID != productDetails.id ||
              completer.isCompleted) {
            continue;
          }
          if (purchase.status == PurchaseStatus.pending) {
            continue;
          }
          if (purchase.status == PurchaseStatus.error) {
            completer.completeError(
              StateError(
                purchase.error?.message ?? 'Store purchase failed.',
              ),
            );
            continue;
          }
          if (purchase.status == PurchaseStatus.purchased ||
              purchase.status == PurchaseStatus.restored) {
            final receipt = StorePurchaseReceipt(
              provider: provider,
              packageId: package.packageId,
              productId: purchase.productID,
              transactionId: purchase.purchaseID ?? '',
              purchaseToken: purchase.verificationData.serverVerificationData,
              verificationData:
                  purchase.verificationData.serverVerificationData,
              verificationSource: purchase.verificationData.source,
            );
            if (purchase.pendingCompletePurchase) {
              await _inAppPurchase.completePurchase(purchase);
            }
            completer.complete(receipt);
          }
        }
      },
      onError: completer.completeError,
    );

    final started = await _inAppPurchase.buyConsumable(
      purchaseParam: PurchaseParam(productDetails: productDetails),
      autoConsume: provider == ConsumerPaymentProvider.playBilling.wireValue,
    );
    if (!started) {
      await subscription.cancel();
      throw StateError('Store purchase could not be started.');
    }

    try {
      return await completer.future.timeout(timeout);
    } finally {
      await subscription.cancel();
    }
  }
}

bool isStorePurchaseProvider(String provider) => _isStoreProvider(provider);

bool _isStoreProvider(String provider) {
  return provider == ConsumerPaymentProvider.iap.wireValue ||
      provider == ConsumerPaymentProvider.playBilling.wireValue;
}
